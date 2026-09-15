from jobops.models.browser import (
    BrowserDryRunPlan,
    BrowserFieldDescriptor,
    BrowserFieldKind,
    BrowserPageSnapshot,
    DryRunAction,
    DryRunOperation,
)


class BrowserDryRunPlanner:
    """Turn an inspected application page into a non-executing preparation plan."""

    def plan(self, snapshot: BrowserPageSnapshot) -> BrowserDryRunPlan:
        actions: list[DryRunAction] = []
        fillable_fields = 0

        for form in snapshot.forms:
            for field in form.fields:
                operation, reason = self._operation(field)
                if operation in {
                    DryRunOperation.FILL,
                    DryRunOperation.SELECT,
                    DryRunOperation.CHOOSE,
                    DryRunOperation.UPLOAD,
                }:
                    fillable_fields += 1
                actions.append(
                    DryRunAction(
                        form_index=field.form_index,
                        field_index=field.field_index,
                        operation=operation,
                        selector=field.selector,
                        label=field.label or field.accessible_name or field.name,
                        required=field.required,
                        reason=reason,
                    )
                )

        return BrowserDryRunPlan(
            url=snapshot.url,
            actions=actions,
            fillable_fields=fillable_fields,
            submit_controls=snapshot.submit_controls,
            submission_allowed=False,
        )

    @staticmethod
    def _operation(field: BrowserFieldDescriptor) -> tuple[DryRunOperation, str]:
        if field.is_submit_control or field.kind is BrowserFieldKind.SUBMIT:
            return (
                DryRunOperation.BLOCKED_SUBMIT,
                "Submit-capable controls are inventoried but unavailable in M3.1 dry-run mode.",
            )
        if field.disabled:
            return DryRunOperation.SKIP, "Disabled controls are not preparation targets."
        if field.kind in {
            BrowserFieldKind.TEXT,
            BrowserFieldKind.EMAIL,
            BrowserFieldKind.TELEPHONE,
            BrowserFieldKind.URL,
            BrowserFieldKind.NUMBER,
            BrowserFieldKind.DATE,
            BrowserFieldKind.TEXTAREA,
        }:
            return DryRunOperation.FILL, "Text-like control can be prepared after field mapping."
        if field.kind is BrowserFieldKind.SELECT:
            return DryRunOperation.SELECT, "Select control requires an option mapping."
        if field.kind in {BrowserFieldKind.CHECKBOX, BrowserFieldKind.RADIO}:
            return DryRunOperation.CHOOSE, "Choice control requires an explicit candidate value."
        if field.kind is BrowserFieldKind.FILE:
            return DryRunOperation.UPLOAD, "File input can later receive an approved document."
        if field.kind is BrowserFieldKind.HIDDEN:
            return DryRunOperation.SKIP, "Hidden controls are not user-answer targets."
        return DryRunOperation.REVIEW, "Control needs manual or adapter-specific classification."
