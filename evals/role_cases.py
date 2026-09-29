"""Human role-holdout annotations; deliberately separate from extractor fields.

PR B validates this metadata but never runs the current-amount role heuristic.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator

from bill_lens.contract import DecimalString


class RoleAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: DecimalString
    printed_label: StrictStr
    role: Literal["amount_due", "previous_balance", "payment", "credit", "overdue", "other_total"]

    @field_validator("printed_label")
    @classmethod
    def nonblank_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("printed label must not be blank")
        return value


class RoleCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    current_bill_amount: DecimalString | None
    current_label: StrictStr | None
    shape: Literal["A", "B", "C", "D", "E", "F", "G", "H"]
    printed_distractors: list[RoleAnnotation]

    @model_validator(mode="after")
    def label_for_printed_current_only(self):
        if (self.current_bill_amount is None) != (self.current_label is None):
            raise ValueError("current label must be null exactly when current amount is null")
        if self.current_label is not None and not self.current_label.strip():
            raise ValueError("current label must not be blank")
        return self
