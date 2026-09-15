import yaml

from jobops.models.resume_evidence import ResumeEvidenceBase


def parse_resume_evidence_yaml(content: str) -> ResumeEvidenceBase:
    payload = yaml.safe_load(content)
    return ResumeEvidenceBase.model_validate(payload)
