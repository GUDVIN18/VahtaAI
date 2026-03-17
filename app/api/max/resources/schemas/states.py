from enum import Enum


class UserState(str, Enum):
    PENDING_OUTREACH = "pending_outreach"
    GET_USER_INFO="get_user_info"
    STATE_NEW = "new"
    STATE_AWAITING_RELEVANCE = "awaiting_relevance"
    STATE_COLLECTING = "collecting"
    STATE_AWAITING_SELECTION_CONSENT = "awaiting_selection_consent"
    STATE_STEP_1_DONE = "step_1_done"
    STATE_STEP_2 = "step_2"
    STATE_STEP_2_DONE = "step_2_done"
    STATE_STEP_3="step_3"
    STATE_CLOSED = "closed"