"""Seed a local DataHub instance with the Steward Squad demo fixture.

Reads the same ``examples/retail_finance_graph.json`` the offline demo uses and
emits it into a running DataHub via the official acryl-datahub SDK, so the LIVE
MCP loop detects the *same* governance risks (owner gaps, PII columns, lineage
blast radius) against a real catalog.

This is a live-path bootstrap helper — it uses acryl-datahub (the optional
``live`` extra), NOT the stdlib-only offline package.

Usage:
    export DATAHUB_GMS_URL=http://localhost:8080
    export DATAHUB_GMS_TOKEN=<token>   # optional for local quickstart
    python scripts/ingest_fixture_to_datahub.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    AuditStampClass,
    ChangeAuditStampsClass,
    DashboardInfoClass,
    DatasetLineageTypeClass,
    DatasetPropertiesClass,
    DateTypeClass,
    DomainPropertiesClass,
    DomainsClass,
    GlobalTagsClass,
    GlossaryTermAssociationClass,
    GlossaryTermInfoClass,
    GlossaryTermsClass,
    MLModelPropertiesClass,
    NumberTypeClass,
    OtherSchemaClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
    SchemaFieldClass,
    SchemaFieldDataTypeClass,
    SchemaMetadataClass,
    StringTypeClass,
    TagAssociationClass,
    TagPropertiesClass,
    TimeTypeClass,
    UpstreamClass,
    UpstreamLineageClass,
)

FIXTURE = Path("examples/retail_finance_graph.json")
NOW_MS = 1_690_000_000_000
_STAMP = AuditStampClass(time=NOW_MS, actor="urn:li:corpuser:datahub")

_TYPE_MAP = {
    "varchar": StringTypeClass,
    "string": StringTypeClass,
    "number": NumberTypeClass,
    "timestamp": TimeTypeClass,
    "date": DateTypeClass,
}


def _field_type(native: str) -> SchemaFieldDataTypeClass:
    cls = _TYPE_MAP.get(native.lower(), StringTypeClass)
    return SchemaFieldDataTypeClass(type=cls())


def _domain_urn(name: str) -> str:
    return f"urn:li:domain:{name}"


def _collect_tag_urns(graph: dict) -> set[str]:
    urns: set[str] = set()
    for asset in graph["assets"]:
        for tag in asset.get("tags", []):
            urns.add(tag if tag.startswith("urn:li:tag:") else f"urn:li:tag:{tag}")
        for col in asset.get("columns", []):
            for tag in col.get("tags", []):
                urns.add(tag if tag.startswith("urn:li:tag:") else f"urn:li:tag:{tag}")
    # The squad proposes this tag as a writeback; it must exist to be attachable.
    urns.add("urn:li:tag:PII")
    return urns


def _tag_assoc(tags: list[str]) -> list[TagAssociationClass]:
    out = []
    for tag in tags:
        urn = tag if tag.startswith("urn:li:tag:") else f"urn:li:tag:{tag}"
        out.append(TagAssociationClass(tag=urn))
    return out


def _term_assoc(terms: list[str]) -> list[GlossaryTermAssociationClass]:
    return [GlossaryTermAssociationClass(urn=t) for t in terms]


def _mcps_for_dataset(asset: dict) -> list[MetadataChangeProposalWrapper]:
    urn = asset["urn"]
    mcps: list[MetadataChangeProposalWrapper] = []

    custom_props = {
        "usage_30d": str(asset.get("usage_30d", 0)),
        "certified": str(asset.get("certified", False)).lower(),
        "domain": asset.get("domain", ""),
        "env": asset.get("env", "PROD"),
        "table": asset.get("properties", {}).get("table", asset["name"]),
    }
    mcps.append(
        MetadataChangeProposalWrapper(
            entityUrn=urn,
            aspect=DatasetPropertiesClass(
                name=asset["name"],
                description=asset.get("description", ""),
                customProperties=custom_props,
            ),
        )
    )

    fields = []
    for col in asset.get("columns", []):
        fields.append(
            SchemaFieldClass(
                fieldPath=col["name"],
                type=_field_type(col.get("native_type", "string")),
                nativeDataType=col.get("native_type", "string"),
                description=col.get("description", ""),
                globalTags=GlobalTagsClass(tags=_tag_assoc(col["tags"]))
                if col.get("tags")
                else None,
                glossaryTerms=GlossaryTermsClass(
                    terms=_term_assoc(col["terms"]), auditStamp=_STAMP
                )
                if col.get("terms")
                else None,
            )
        )
    if fields:
        mcps.append(
            MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=SchemaMetadataClass(
                    schemaName=asset["name"],
                    platform=f"urn:li:dataPlatform:{asset['platform']}",
                    version=0,
                    hash="",
                    platformSchema=OtherSchemaClass(rawSchema=""),
                    fields=fields,
                ),
            )
        )

    _add_common_aspects(mcps, asset)
    return mcps


def _add_common_aspects(mcps: list, asset: dict) -> None:
    urn = asset["urn"]
    if asset.get("owner"):
        mcps.append(
            MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=OwnershipClass(
                    owners=[
                        OwnerClass(owner=asset["owner"], type=OwnershipTypeClass.DATAOWNER)
                    ]
                ),
            )
        )
    if asset.get("tags"):
        mcps.append(
            MetadataChangeProposalWrapper(
                entityUrn=urn, aspect=GlobalTagsClass(tags=_tag_assoc(asset["tags"]))
            )
        )
    if asset.get("terms"):
        mcps.append(
            MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=GlossaryTermsClass(terms=_term_assoc(asset["terms"]), auditStamp=_STAMP),
            )
        )
    if asset.get("domain"):
        mcps.append(
            MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=DomainsClass(domains=[_domain_urn(asset["domain"])]),
            )
        )


def _mcps_for_dashboard(asset: dict) -> list[MetadataChangeProposalWrapper]:
    mcps = [
        MetadataChangeProposalWrapper(
            entityUrn=asset["urn"],
            aspect=DashboardInfoClass(
                title=asset["name"],
                description=asset.get("description", ""),
                lastModified=ChangeAuditStampsClass(created=_STAMP, lastModified=_STAMP),
                customProperties={
                    "usage_30d": str(asset.get("usage_30d", 0)),
                    "domain": asset.get("domain", ""),
                },
            ),
        )
    ]
    _add_common_aspects(mcps, asset)
    return mcps


def _mcps_for_mlmodel(asset: dict) -> list[MetadataChangeProposalWrapper]:
    mcps = [
        MetadataChangeProposalWrapper(
            entityUrn=asset["urn"],
            aspect=MLModelPropertiesClass(
                name=asset["name"],
                description=asset.get("description", ""),
                customProperties={
                    "usage_30d": str(asset.get("usage_30d", 0)),
                    "domain": asset.get("domain", ""),
                },
            ),
        )
    ]
    _add_common_aspects(mcps, asset)
    return mcps


def _lineage_mcps(graph: dict) -> list[MetadataChangeProposalWrapper]:
    """Dataset->dataset upstreamLineage (the edges the squad walks for blast radius)."""
    downstream_to_upstreams: dict[str, list[str]] = {}
    dataset_urns = {
        a["urn"] for a in graph["assets"] if a.get("entity_type") == "dataset"
    }
    for edge in graph.get("lineage", []):
        up, down = edge["upstream"], edge["downstream"]
        if up in dataset_urns and down in dataset_urns:
            downstream_to_upstreams.setdefault(down, []).append(up)
    # Bridge dataset->datajob->dataset so raw.payments reaches fct_revenue directly.
    for edge in graph.get("lineage", []):
        up, down = edge["upstream"], edge["downstream"]
        if up in dataset_urns and down not in dataset_urns:
            for edge2 in graph.get("lineage", []):
                if edge2["upstream"] == down and edge2["downstream"] in dataset_urns:
                    downstream_to_upstreams.setdefault(edge2["downstream"], []).append(up)

    mcps = []
    for down, ups in downstream_to_upstreams.items():
        upstreams = [
            UpstreamClass(dataset=u, type=DatasetLineageTypeClass.TRANSFORMED)
            for u in sorted(set(ups))
        ]
        mcps.append(
            MetadataChangeProposalWrapper(
                entityUrn=down, aspect=UpstreamLineageClass(upstreams=upstreams)
            )
        )
    return mcps


def main() -> int:
    gms = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
    token = os.environ.get("DATAHUB_GMS_TOKEN") or None
    graph = json.loads(FIXTURE.read_text(encoding="utf-8"))

    emitter = DatahubRestEmitter(gms_server=gms, token=token)
    emitter.test_connection()
    print(f"Connected to DataHub GMS at {gms}")

    mcps: list[MetadataChangeProposalWrapper] = []

    # 1) Reference entities: tags, glossary terms, domains (so associations resolve
    #    and the PII writeback tool can validate its target tag exists).
    for tag_urn in sorted(_collect_tag_urns(graph)):
        name = tag_urn.split(":")[-1]
        mcps.append(
            MetadataChangeProposalWrapper(entityUrn=tag_urn, aspect=TagPropertiesClass(name=name))
        )
    for term_urn, definition in graph.get("glossary", {}).items():
        name = term_urn.split(":")[-1]
        mcps.append(
            MetadataChangeProposalWrapper(
                entityUrn=term_urn,
                aspect=GlossaryTermInfoClass(
                    name=name, definition=definition, termSource="INTERNAL"
                ),
            )
        )
    for domain_name in sorted({a.get("domain", "") for a in graph["assets"] if a.get("domain")}):
        mcps.append(
            MetadataChangeProposalWrapper(
                entityUrn=_domain_urn(domain_name),
                aspect=DomainPropertiesClass(name=domain_name),
            )
        )

    # 2) Assets.
    for asset in graph["assets"]:
        kind = asset.get("entity_type")
        if kind == "dataset":
            mcps.extend(_mcps_for_dataset(asset))
        elif kind == "dashboard":
            mcps.extend(_mcps_for_dashboard(asset))
        elif kind == "mlmodel":
            mcps.extend(_mcps_for_mlmodel(asset))
        # datajob/dataflow omitted: not needed for the squad's detections.

    # 3) Lineage.
    mcps.extend(_lineage_mcps(graph))

    print(f"Emitting {len(mcps)} metadata change proposals...")
    for i, mcp in enumerate(mcps, 1):
        emitter.emit(mcp)
        if i % 10 == 0:
            print(f"  emitted {i}/{len(mcps)}")
    print(f"Done. Emitted {len(mcps)} aspects across {len(graph['assets'])} assets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
