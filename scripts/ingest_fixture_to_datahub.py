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
    AssertionInfoClass,
    AssertionResultClass,
    AssertionResultTypeClass,
    AssertionRunEventClass,
    AssertionRunStatusClass,
    AssertionStdOperatorClass,
    AssertionStdParameterClass,
    AssertionStdParametersClass,
    AssertionStdParameterTypeClass,
    AssertionTypeClass,
    AuditStampClass,
    ChangeAuditStampsClass,
    DashboardInfoClass,
    DataFlowInfoClass,
    DataJobInfoClass,
    DataJobInputOutputClass,
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
    SqlAssertionInfoClass,
    SqlAssertionTypeClass,
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


def _mcps_for_dashboard(asset: dict, input_datasets: list[str]) -> list[MetadataChangeProposalWrapper]:
    mcps = [
        MetadataChangeProposalWrapper(
            entityUrn=asset["urn"],
            aspect=DashboardInfoClass(
                title=asset["name"],
                description=asset.get("description", ""),
                lastModified=ChangeAuditStampsClass(created=_STAMP, lastModified=_STAMP),
                # Input datasets create dataset->dashboard lineage, so the squad
                # sees the dashboard as downstream production blast radius.
                datasets=sorted(input_datasets) or None,
                customProperties={
                    "usage_30d": str(asset.get("usage_30d", 0)),
                    "domain": asset.get("domain", ""),
                },
            ),
        )
    ]
    _add_common_aspects(mcps, asset)
    return mcps


def _mcps_for_datajob(
    asset: dict, inputs: list[str], outputs: list[str]
) -> list[MetadataChangeProposalWrapper]:
    """Emit the DataFlow parent, the DataJob, and its input/output lineage.

    DataJobInputOutput wires raw.payments -> job -> fct_revenue, so get_lineage
    surfaces the job as a direct neighbour and the squad flags its blast radius.
    """
    # DataJob URN embeds its parent DataFlow: urn:li:dataJob:(<dataFlowUrn>,<id>)
    flow_urn = asset["urn"].split("(", 1)[1].rsplit(",", 1)[0]
    orchestrator = flow_urn.split("(", 1)[1].split(",", 1)[0]
    mcps = [
        MetadataChangeProposalWrapper(
            entityUrn=flow_urn,
            aspect=DataFlowInfoClass(name=asset["name"].split(".")[0], customProperties={}),
        ),
        MetadataChangeProposalWrapper(
            entityUrn=asset["urn"],
            aspect=DataJobInfoClass(
                name=asset["name"],
                type=orchestrator.upper() if orchestrator else "COMMAND",
                description=asset.get("description", ""),
                customProperties={
                    "usage_30d": str(asset.get("usage_30d", 0)),
                    "domain": asset.get("domain", ""),
                },
            ),
        ),
        MetadataChangeProposalWrapper(
            entityUrn=asset["urn"],
            aspect=DataJobInputOutputClass(
                inputDatasets=sorted(inputs), outputDatasets=sorted(outputs)
            ),
        ),
    ]
    _add_common_aspects(mcps, asset)
    return mcps


def _safe_id(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text).strip("-")


def _assertion_mcps(graph: dict) -> list[MetadataChangeProposalWrapper]:
    """Emit each fixture assertion as an Assertion entity + a run event.

    A FAILURE run event makes DataHub compute an ASSERTIONS 'health' signal on the
    dataset (FAIL), which the live adapter reads to raise a quality finding —
    without relying on the cloud-only get_dataset_assertions tool.
    """
    mcps: list[MetadataChangeProposalWrapper] = []
    for asset in graph["assets"]:
        dataset_urn = asset["urn"]
        for idx, assertion in enumerate(asset.get("assertions", [])):
            a_urn = f"urn:li:assertion:steward-{_safe_id(asset['name'])}-{idx}"
            statement = (
                assertion.get("notes")
                or f"{assertion.get('kind', 'data quality')} check for {asset['name']}"
            )
            mcps.append(
                MetadataChangeProposalWrapper(
                    entityUrn=a_urn,
                    aspect=AssertionInfoClass(
                        type=AssertionTypeClass.SQL,
                        description=assertion.get("name", statement),
                        sqlAssertion=SqlAssertionInfoClass(
                            type=SqlAssertionTypeClass.METRIC,
                            entity=dataset_urn,
                            statement=statement,
                            operator=AssertionStdOperatorClass.EQUAL_TO,
                            parameters=AssertionStdParametersClass(
                                value=AssertionStdParameterClass(
                                    value="0", type=AssertionStdParameterTypeClass.NUMBER
                                )
                            ),
                        ),
                    ),
                )
            )
            failed = str(assertion.get("status", "")).upper() in {"FAIL", "FAILED", "ERROR"}
            mcps.append(
                MetadataChangeProposalWrapper(
                    entityUrn=a_urn,
                    aspect=AssertionRunEventClass(
                        timestampMillis=NOW_MS,
                        runId=f"steward-{idx}",
                        asserteeUrn=dataset_urn,
                        assertionUrn=a_urn,
                        status=AssertionRunStatusClass.COMPLETE,
                        result=AssertionResultClass(
                            type=AssertionResultTypeClass.FAILURE
                            if failed
                            else AssertionResultTypeClass.SUCCESS
                        ),
                    ),
                )
            )
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
    # raw.payments -> fct_revenue now flows through the real datajob (see
    # _mcps_for_datajob), so no synthetic dataset->dataset bridge is needed.

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

    # Precompute cross-type lineage relationships from the fixture edges.
    dataset_urns = {a["urn"] for a in graph["assets"] if a.get("entity_type") == "dataset"}
    inputs_of: dict[str, list[str]] = {}   # entity <- upstream datasets
    outputs_of: dict[str, list[str]] = {}  # entity -> downstream datasets
    for edge in graph.get("lineage", []):
        up, down = edge["upstream"], edge["downstream"]
        if up in dataset_urns:
            inputs_of.setdefault(down, []).append(up)
        if down in dataset_urns:
            outputs_of.setdefault(up, []).append(down)

    # 2) Assets.
    for asset in graph["assets"]:
        kind = asset.get("entity_type")
        urn = asset["urn"]
        if kind == "dataset":
            mcps.extend(_mcps_for_dataset(asset))
        elif kind == "dashboard":
            mcps.extend(_mcps_for_dashboard(asset, inputs_of.get(urn, [])))
        elif kind == "mlmodel":
            mcps.extend(_mcps_for_mlmodel(asset))
        elif kind == "datajob":
            mcps.extend(_mcps_for_datajob(asset, inputs_of.get(urn, []), outputs_of.get(urn, [])))

    # 3) Dataset->dataset lineage + assertion run events.
    mcps.extend(_lineage_mcps(graph))
    mcps.extend(_assertion_mcps(graph))

    print(f"Emitting {len(mcps)} metadata change proposals...")
    for i, mcp in enumerate(mcps, 1):
        emitter.emit(mcp)
        if i % 10 == 0:
            print(f"  emitted {i}/{len(mcps)}")
    print(f"Done. Emitted {len(mcps)} aspects across {len(graph['assets'])} assets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
