from typing import Dict, List

from utils.logger import get_logger

from schemas.geometry_schema import (
    FilterResult,
    FilterStatistics,
    FilteredEntity,
)


logger = get_logger(__name__)


TEXT_ENTITY_TYPES = {
    "TEXT",
    "MTEXT",
}

# Text roles that contain supervision signals (keep these)
SUPERVISION_ROLES = {
    "dimension_value",
    "diameter_value",
    "radius_value",
    "angle_value",
    "tolerance",
    "thread_callout",
}


class TextFilter:
    """
    Filter text entities: preserve supervision-bearing text,
    quarantine pure annotations.

    Supervision text (dimension values, tolerances, callouts)
    is KEPT for downstream dimension inference training.
    Pure annotations (titles, notes) are QUARANTINED.
    """

    def filter(self, entities: List[Dict]) -> FilterResult:

        kept = []
        quarantined = []
        removed = []

        for entity in entities:

            entity_type = entity["entity_type"]

            if entity_type in TEXT_ENTITY_TYPES:
                geometry = entity.get("geometry", {})
                text_role = geometry.get("text_role", "annotation")

                if text_role in SUPERVISION_ROLES:
                    # Preserve: contains dimension supervision signal
                    kept.append(entity)
                else:
                    # Check text content for engineering rules note
                    import re
                    text_val = geometry.get("text") or geometry.get("content") or ""
                    
                    t = text_val.upper()
                    admin_patterns = [
                        r'\bDWG\b', r'\bDRAWING\b', r'\bREV\b', r'\bREVISION\b',
                        r'\bSHEET\b', r'\bSCALE\b', r'\bTITLE\b', r'\bDATE\b',
                        r'\bDRAWN\b', r'\bAPPROVED\b', r'\bCOMPANY\b', r'\bAUTHOR\b',
                        r'\bPAGE\b', r'\bFILE\b'
                    ]
                    eng_patterns = [
                        r'\bFILLET\b', r'\bRADIUS\b', r'\bTOLERANCE\b', r'±',
                        r'\bCHAMFER\b', r'\bBREAK\s+ALL\s+SHARP\b', r'\bBREAK\s+SHARP\b',
                        r'\bREMOVE\s+BURRS\b', r'\bMATL\b', r'\bMATERIAL\b', r'\bALUMINUM\b',
                        r'\bCOPPER\b', r'\bSTEEL\b', r'\bFINISH\b', r'\bSURFACE\b',
                        r'\bTHREAD\b', r'\bWELD\b', r'\bBEVEL\b', r'\bANODIZE\b',
                        r'\bPLATING\b', r'\bCOATING\b', r'\bHEAT\s+TREAT\b', r'\bHEAT-TREAT\b',
                        r'\bROUTING\b', r'\bDIFFERENTIAL\b', r'\bSPOKE\b', r'\bGOLD\s+PLATED\b',
                        r'\bHEM\b', r'\bBSPP\b', r'\bBSPT\b', r'\bNPT\b', r'\bUNC\b', r'\bUNF\b',
                        r'\bMETRIC\b', r'\bISOLATION\b', r'\bLAMINATED\b', r'\bRETURN\s+SLOT\b',
                        r'\bVANE\b', r'\bCONE\b', r'\bUNDERCUT\b', r'\bO-RING\b', r'\bSEAL\b',
                        r'\bGROOVE\b', r'\bCLEARANCE\b', r'\bEDGE\b'
                    ]
                    
                    is_admin = any(re.search(pat, t) for pat in admin_patterns)
                    is_eng = any(re.search(pat, t) for pat in eng_patterns)
                    
                    if is_eng and not is_admin:
                        # Recover engineering notes! Mark their role as general_note
                        geometry["text_role"] = "general_note"
                        kept.append(entity)
                    else:
                        # Quarantine: pure annotation (not supervision or engineering note)
                        quarantined.append(
                            FilteredEntity(
                                entity=entity,
                                reason=f"non_supervision_text:{text_role}",
                            )
                        )
                continue

            kept.append(entity)

        stats = FilterStatistics(
            input_entities=len(entities),
            kept_entities=len(kept),
            quarantined_entities=len(quarantined),
            removed_entities=len(removed),
        )

        supervision_kept = sum(
            1 for e in kept if e.get("entity_type") in TEXT_ENTITY_TYPES
        )

        logger.info(
            f"TextFilter: kept={len(kept)} "
            f"(supervision_text={supervision_kept}) "
            f"quarantined={len(quarantined)}"
        )

        return FilterResult(
            kept_entities=kept,
            quarantined_entities=quarantined,
            removed_entities=removed,
            statistics=stats,
        )
