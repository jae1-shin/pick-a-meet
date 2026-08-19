from collections import Counter
from collections.abc import Iterable


def part_registration_allowed(
    *,
    candidate_part_id: int,
    applicant_part_ids: Iterable[int],
    active_part_member_count: int,
    distribution_meeting_count: int,
) -> bool:
    """Return whether the candidate satisfies the per-meeting part spread rule."""
    part_counts = Counter(applicant_part_ids)
    same_part_count = part_counts[candidate_part_id]

    if same_part_count == 0:
        return True
    if same_part_count >= 2:
        return False
    if active_part_member_count <= distribution_meeting_count:
        return False
    return all(count < 2 for count in part_counts.values())
