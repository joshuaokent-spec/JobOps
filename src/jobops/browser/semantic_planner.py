from jobops.models.application_question import HandlingRoute
from jobops.models.form_mapping import (
    ApplicationFieldSemantic,
    SemanticPageMapping,
    SemanticPreparationAction,
    SemanticPreparationOperation,
    SemanticPreparationPlan,
)


class SemanticPreparationPlanner:
    """Route semantic field mappings into M2 preparation/review paths without browser writes."""

    def plan(self, mapping: SemanticPageMapping) -> SemanticPreparationPlan:
        actions = [self._action(item) for item in mapping.mappings]
        return SemanticPreparationPlan(
            url=mapping.page.url,
            actions=actions,
            fact_resolution_fields=sum(
                action.operation is SemanticPreparationOperation.RESOLVE_FACT
                for action in actions
            ),
            review_fields=sum(
                action.operation
                in {
                    SemanticPreparationOperation.DRAFT_WITH_REVIEW,
                    SemanticPreparationOperation.HUMAN_REVIEW,
                }
                for action in actions
            ),
            unresolved_fields=sum(
                action.operation is SemanticPreparationOperation.ESCALATE
                for action in actions
            ),
            submit_controls=sum(
                action.operation is SemanticPreparationOperation.BLOCKED_SUBMIT
                for action in actions
            ),
            submission_allowed=False,
        )

    @staticmethod
    def _action(mapping) -> SemanticPreparationAction:
        if mapping.semantic is ApplicationFieldSemantic.SUBMIT_CONTROL:
            return SemanticPreparationAction(
                mapping=mapping,
                operation=SemanticPreparationOperation.BLOCKED_SUBMIT,
                reason="Submit controls remain unavailable until the explicit M3 submit gate.",
            )
        if mapping.route is HandlingRoute.AUTO_FILL:
            return SemanticPreparationAction(
                mapping=mapping,
                operation=SemanticPreparationOperation.RESOLVE_FACT,
                reason=(
                    "Resolve the mapped fact key through verified candidate data before any "
                    "future browser fill step."
                ),
            )
        if mapping.route is HandlingRoute.DRAFT_WITH_REVIEW:
            return SemanticPreparationAction(
                mapping=mapping,
                operation=SemanticPreparationOperation.DRAFT_WITH_REVIEW,
                reason="Use the existing M2 draft/review path; do not fill the browser yet.",
            )
        if mapping.route is HandlingRoute.HUMAN_REVIEW:
            return SemanticPreparationAction(
                mapping=mapping,
                operation=SemanticPreparationOperation.HUMAN_REVIEW,
                reason="Consequential or sensitive field requires explicit human review.",
            )
        return SemanticPreparationAction(
            mapping=mapping,
            operation=SemanticPreparationOperation.ESCALATE,
            reason="Field meaning remains unresolved and must not be guessed.",
        )
