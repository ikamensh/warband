"""Playable campaigns and their stable ids, shared by the campaign screen, CLI and save loader."""

from warband.story.campaign import Campaign, Mission
from warband.story.missions import CAMPAIGN

CAMPAIGNS = (CAMPAIGN,)
DEFAULT_CAMPAIGN = CAMPAIGN


def get_campaign(campaign_id: str) -> Campaign:
    """Find the campaign named by a progress file or mission save."""
    for campaign in CAMPAIGNS:
        if campaign.id == campaign_id:
            return campaign
    raise KeyError(f"no campaign {campaign_id!r} in this version of Warband")


def find_mission(mission_id: str) -> tuple[Campaign, Mission]:
    """Resolve a direct mission launch. Mission ids are unique across the catalogue."""
    matches = [(campaign, mission) for campaign in CAMPAIGNS for mission in campaign.missions if mission.id == mission_id]
    if len(matches) != 1:
        raise KeyError(f"mission {mission_id!r} is {'ambiguous' if matches else 'not in this version of Warband'}")
    return matches[0]
