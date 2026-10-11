"""Assemble automatic surface styles in their preserved cascade order."""

from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_styles import AUTOMATIC_PROFILE_RULES
from dlc_gait_assembly.runway.automatic.review.client.automatic_review_styles import AUTOMATIC_REVIEW_RULES
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_styles import AUTOMATIC_RUN_RULES
from dlc_gait_assembly.shared.client.theme.theme_application_styles import stylesheet

AUTOMATIC_WORKSPACE_RULES = (
    (
        12,
        """QLabel#AutomationPanelTitle {
    color: {theme.TEXT};
    font-size: 15px;
    font-weight: 700;
}
""",
    ),
)
AUTOMATED_PIPELINE_QSS = "".join(
    rule
    for _, rule in sorted(
        (*AUTOMATIC_WORKSPACE_RULES, *AUTOMATIC_PROFILE_RULES, *AUTOMATIC_RUN_RULES, *AUTOMATIC_REVIEW_RULES)
    )
)


def automated_pipeline_stylesheet():
    return stylesheet(AUTOMATED_PIPELINE_QSS)
