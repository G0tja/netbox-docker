#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from netboxlabs.diode.sdk import DiodeClient
from netboxlabs.diode.sdk.ingester import (
    Device,
    Entity,
)
import base64

LOG = logging.getLogger("xen-diode")

XO_BASE_URL = "http://xoa.loe.internal"
XO_TOKEN = "<secret>"
XO_TOKEN_HEADER: Optional[str] = None
XO_USER: Optional[str] = None
XO_PASS: Optional[str] = None
XO_ENDPOINTS = "/api/vm,/api/host"

DIODE_URL = "grpc://netbox.loe.internal:8080/diode"
DIODE_TOKEN: Optional[str] = None
DIODE_TOKEN_HEADER: Optional[str] = None

DIODE_TIMEOUT = 10
DIODE_CLIENT_ID: Optional[str] = "<secret>"
DIODE_CLIENT_SECRET: Optional[str] = "<secret>"



def make_session(xo_token: Optional[str], xo_token_header: Optional[str], username: Optional[str], password: Optional[str]) -> requests.Session:
	s = requests.Session()
	s.headers.update({"Accept": "application/json"})
	if xo_token:
		header = xo_token_header or "Authorization"
		# default to Bearer for XO tokens; user can override header value if needed
		s.headers.update({header: f"Bearer {xo_token}"})
	elif username and password:
		s.auth = (username, password)
	return s


def build_url(base: str, path: str) -> str:
	if path.startswith("/"):
		return base.rstrip("/") + path
	return base.rstrip("/") + "/" + path


def fetch_endpoint(session: requests.Session, base: str, path: str, timeout: int = 10) -> Any:
	url = build_url(base, path)
	LOG.debug("GET %s", url)
	r = session.get(url, timeout=timeout)
	r.raise_for_status()
	# Some XO endpoints return lists, others dicts; return parsed JSON
	return r.json()


def summarize_response(obj: Any) -> Dict[str, Any]:
	if isinstance(obj, list):
		return {"count": len(obj)}
	if isinstance(obj, dict):
		# Many XO endpoints return dict id -> object
		if all(isinstance(v, dict) for v in obj.values()):
			return {"count": len(obj)}
		# Fallback: include top-level keys
		return {"keys": list(obj.keys())[:20]}
	# primitive
	return {"value": obj}


def build_entities_from_results(results: Dict[str, Any], base_url: str, timestamp: str) -> List[Entity]:
	"""Build Diode Entity list (Devices) from the fetched XO metrics.

	For each endpoint we create a synthetic Device entity whose tags
	encode simple metric key/value pairs (e.g. count). This keeps the
	ingest simple and allows searching by tag in NetBox later.
	"""
	entities: List[Entity] = []
	for ep, metric in results.items():
		# build a short, filesystem-friendly name
		safe_ep = ep.strip("/").replace("/", "-") or "root"
		name = f"xo-{safe_ep}-{timestamp}"

		# tags: include endpoint and metric entries (simple scalar values)
		tags: List[str] = [f"endpoint:{ep}", "source:xen-orchestra"]
		if isinstance(metric, dict):
			for k, v in metric.items():
				# include only small scalar values as tags
				if isinstance(v, (str, int, float, bool)):
					tags.append(f"{k}:{v}")
		# add a link back to the source XO instance
		tags.append(f"xo_url:{base_url}")

		device = Device(
			name=name,
			device_type="xo-summary",
			platform="xen-orchestra",
			manufacturer="xen-orchestra",
			site="xen-orchestra",
			role="summary",
			serial=str(metric.get("count")) if isinstance(metric, dict) and metric.get("count") is not None else None,
			asset_tag=None,
			status="active",
			tags=tags,
		)

		entities.append(Entity(device=device))

	return entities


def ingest_with_sdk(target: str, app_name: str, app_version: str, entities: List[Entity]) -> None:
	LOG.debug("Ingesting %d entities to %s", len(entities), target)
	with DiodeClient(target=target, app_name=app_name, app_version=app_version) as client:
		response = client.ingest(entities=entities)
		if response.errors:
			LOG.error("Diode ingest returned errors: %s", response.errors)
			# print errors for user visibility
			print("Diode ingest errors:", response.errors)
		else:
			LOG.info("Ingest successful: %s", getattr(response, "message", "ok"))


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Fetch Xen Orchestra resources and POST summaries to NetBox Diode API")
	p.add_argument("--dry-run", action="store_true", help="Don't POST to Diode; print the payload")
	p.add_argument("--timeout", type=int, default=int(os.environ.get("DIODE_TIMEOUT", str(DIODE_TIMEOUT))), help="HTTP timeout seconds for requests")
	p.add_argument("--verbose", "-v", action="count", default=0, help="Increase verbosity (repeat for more logging)")
	return p.parse_args(argv)


def setup_logging(verbosity: int) -> None:
	level = logging.WARNING
	if verbosity >= 2:
		level = logging.DEBUG
	elif verbosity == 1:
		level = logging.INFO
	logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv: Optional[List[str]] = None) -> int:
	args = parse_args(argv)
	setup_logging(args.verbose)

	endpoints = [e.strip() for e in XO_ENDPOINTS.split(",") if e.strip()]
	session = make_session(XO_TOKEN, XO_TOKEN_HEADER, XO_USER, XO_PASS)

	results: Dict[str, Any] = {}
	timestamp = datetime.now(timezone.utc).isoformat()

	for ep in endpoints:
		try:
			data = fetch_endpoint(session, XO_BASE_URL, ep, timeout=args.timeout)
			results[ep] = summarize_response(data)
		except Exception as e:  # keep gathering other endpoints even if one fails
			LOG.error("Failed to fetch %s: %s", ep, e)
			results[ep] = {"error": str(e)}

	payload = {
		"source": "xen-orchestra",
		"source_url": XO_BASE_URL,
		"timestamp": timestamp,
		"metrics": results,
	}

	if args.dry_run:
		print(json.dumps(payload, indent=2))
		return 0

	# Build Diode entities and ingest via SDK
	entities = build_entities_from_results(results, XO_BASE_URL, timestamp.replace(":", "-"))

	if args.dry_run:
		print("Entities to ingest:")
		for ent in entities:
			# print a compact representation
			print(ent.device.name, ent.device.tags)
		return 0

	# Use the netboxlabs diode SDK. Expect diode URL to be supplied as a
	# gRPC target (e.g. grpc://host:port/diode) per the SDK docs.
	# prepare metadata for Diode auth if client_id/secret are set
	metadata = None
	if DIODE_CLIENT_ID and DIODE_CLIENT_SECRET:
		token = base64.b64encode(f"{DIODE_CLIENT_ID}:{DIODE_CLIENT_SECRET}".encode()).decode()
		metadata = [("authorization", f"Basic {token}")]

	try:
		if metadata:
			# try passing metadata to ingest call
			LOG.debug("Using Basic auth metadata for Diode client")
			with DiodeClient(target=DIODE_URL, app_name="xen-diode", app_version="0.1.0") as client:
				response = client.ingest(entities=entities, metadata=metadata)
				if response.errors:
					LOG.error("Diode ingest returned errors: %s", response.errors)
					print("Diode ingest errors:", response.errors)
					return 2
				return 0
		else:
			ingest_with_sdk(target=DIODE_URL, app_name="xen-diode", app_version="0.1.0", entities=entities)
			return 0
	except TypeError:
		# fallback: SDK doesn't accept metadata in ingest signature, try client-level metadata
		LOG.debug("ingest() didn't accept metadata; attempting client-level metadata")
		try:
			# attempt to construct DiodeClient with metadata kwarg
			with DiodeClient(target=DIODE_URL, app_name="xen-diode", app_version="0.1.0", metadata=metadata) as client:
				response = client.ingest(entities=entities)
				if response.errors:
					LOG.error("Diode ingest returned errors: %s", response.errors)
					print("Diode ingest errors:", response.errors)
					return 2
				return 0
		except Exception:
			LOG.exception("Failed to ingest to Diode via SDK using metadata fallback")
			return 2
	except Exception:
		LOG.exception("Failed to ingest to Diode via SDK")
		return 2


if __name__ == "__main__":
	sys.exit(main())

