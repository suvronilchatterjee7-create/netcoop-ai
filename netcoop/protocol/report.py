"""The unified diagnostic report.

Top-level keys are exactly the organiser's A7 shape. Everything NetCoop adds lives under
the single namespaced key ``x_netcoop`` so the required keys are never altered.
"""

from __future__ import annotations

from enum import StrEnum

from netcoop.protocol.common import F, ProtocolModel


class ReportStatus(StrEnum):
    DIAGNOSED = "diagnosed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NO_FAULT_DETECTED = "no_fault_detected"
    FAILED = "failed"  # the run itself could not complete (e.g. unreadable input)


class EvidenceItem(ProtocolModel):
    metric: str = F("Canonical metric name.")
    value: float = F("Observed summary value, in the unit given in x_netcoop provenance.")
    interpretation: str = F("What the value means relative to its baseline/threshold.")


class EvidenceProvenance(ProtocolModel):
    evidence_index: int = F("Index into supporting_evidence.", ge=0)
    clue_id: str = F("msg_id of the CLUE behind this evidence item.")
    agent: str = F("agent_id that produced the clue.")
    entity_id: str = F("Entity the evidence is about.")
    unit: str = F("Unit of `value`.")
    reference_value: float | str | None = F("Threshold or baseline compared against.")
    config_key: str = F("Config / calibration key of the reference.")
    observation_ids: tuple[str, ...] = F("OBSERVATION msg_ids the clue was computed from.")


class ScoredAlternative(ProtocolModel):
    cause: str = F("Hypothesis type and location, same wording as alternative_causes.")
    score: float = F("Raw evidence score.")
    confidence: float = F("Calibrated confidence.", "ratio", ge=0, le=1)


class DataQualitySummary(ProtocolModel):
    overall: float = F("Aggregate input quality.", "ratio", ge=0, le=1)
    per_entity: dict[str, float] = F("Quality per entity_id.", default={})
    issues: dict[str, int] = F("Count of each issue code seen.", default={})


class CourtroomSummary(ProtocolModel):
    invoked: bool = F("Whether the tie-break ran.")
    contenders: tuple[str, ...] = F("Hypotheses that were argued.", default=())
    rounds: int = F("Debate rounds held.", ge=0, default=0)
    outcome: str = F("'resolved' or 'deferred'.", default="")
    summary: str = F("Short explanation of the ruling.", default="")
    transcript_msg_ids: tuple[str, ...] = F("Trace messages of the debate.", default=())


class RunManifest(ProtocolModel):
    incident_id: str = F("Incident (correlation_id) of the run.")
    input_hash: str = F("SHA-256 over the input files.")
    config_hash: str = F("SHA-256 over config/*.yaml.")
    code_version: str = F("netcoop package version (and git revision if available).")
    protocol_version: str = F("Protocol version used on the board.")
    vocabulary_version: str = F("Controlled vocabulary version.")
    seed: int = F("Seed for any randomness.")


class ReportExtensions(ProtocolModel):
    confidence_category: str = F("Confidence category (boundaries in config).")
    evidence_provenance: tuple[EvidenceProvenance, ...] = F(
        "Trace of each evidence item.", default=()
    )
    alternatives_scored: tuple[ScoredAlternative, ...] = F(
        "Scores of alternative causes.", default=()
    )
    data_quality: DataQualitySummary | None = F("Input quality summary.", default=None)
    courtroom: CourtroomSummary | None = F("Tie-break summary, if relevant.", default=None)
    missing_evidence: tuple[str, ...] = F(
        "What extra data would resolve an abstention.", default=()
    )
    manifest: RunManifest | None = F("Reproducibility manifest.", default=None)


class Report(ProtocolModel):
    incident_id: str = F("Incident identifier.")
    status: ReportStatus = F("Overall outcome.")
    suspected_root_cause: str = F("Root cause in words, or why none can be named.")
    confidence: float = F("Calibrated confidence in the status/root cause.", "ratio", ge=0, le=1)
    affected_devices: tuple[str, ...] = F("entity_ids of affected devices/links/services.")
    supporting_evidence: tuple[EvidenceItem, ...] = F("Evidence behind the conclusion.")
    alternative_causes: tuple[str, ...] = F("Competing explanations with non-trivial support.")
    recommended_actions: tuple[str, ...] = F("Corrective actions for human review.")
    evidence_sources: tuple[str, ...] = F("agent_ids whose evidence was used.")
    limitations: tuple[str, ...] = F("Data problems, missing agents, uncertainty.")
    x_netcoop: ReportExtensions | None = F("NetCoop extensions (namespaced).", default=None)
