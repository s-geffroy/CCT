from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    # Champ inconnu = 422 : un client ne glisse rien que le contrat ne prevoit.
    model_config = ConfigDict(extra="forbid")
