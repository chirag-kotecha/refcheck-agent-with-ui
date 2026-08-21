"""Four single-reference (REF1, open-text) test cases covering each branch."""

from refcheck.schemas import ClaimedDetails

clean = {
    "candidate_name": "Priya Nair",
    "role_applied_for": "Product Manager",
    "claimed_details": ClaimedDetails(
        job_title="Product Manager", company="Northwind Analytics",
        start_date="2021-03", end_date="2024-06",
        responsibilities=["roadmap planning", "cross-functional coordination"],
        reason_for_leaving="Relocated",
    ),
    "raw_input": (
        "Hi, thanks for reaching out about Priya. She was our Product Manager "
        "from March 2021 until she left in June 2024 to relocate. She ran our "
        "roadmap process and worked closely with engineering and design. "
        "Strong performer, very organized, we'd absolutely rehire her if she "
        "were local again. No concerns at all."
    ),
}

date_mismatch = {
    "candidate_name": "Daniel Cho",
    "role_applied_for": "Data Analyst",
    "claimed_details": ClaimedDetails(
        job_title="Data Analyst", company="Bluepeak Retail",
        start_date="2020-01", end_date="2023-01",
        responsibilities=["sales reporting", "inventory dashboards"],
        reason_for_leaving="Career growth",
    ),
    "raw_input": (
        "Sure, I can talk about Daniel. Let me think -- he joined us, I want "
        "to say around mid-2021, and left maybe early 2023. He worked on "
        "reporting for the sales team. He was fine, did what was asked."
    ),
}

hedging_reference = {
    "candidate_name": "Marcus Webb",
    "role_applied_for": "Account Executive",
    "claimed_details": ClaimedDetails(
        job_title="Account Executive", company="Sable & Finch Insurance",
        start_date="2022-02", end_date="2024-02",
        responsibilities=["client accounts", "renewals"],
        reason_for_leaving="Seeking new opportunity",
    ),
    "raw_input": (
        "Yeah, Marcus worked here, February 2022 to February 2024, account "
        "executive, that's right. Um, he handled client renewals, that's "
        "accurate. As for rehiring... I'd rather not get into that, honestly. "
        "He did his job. I don't think I have anything else to add."
    ),
}

title_inflation = {
    "candidate_name": "Renee Ostrowski",
    "role_applied_for": "Engineering Manager",
    "claimed_details": ClaimedDetails(
        job_title="Senior Engineering Manager", company="Cascade Robotics",
        start_date="2019-09", end_date="2023-11",
        responsibilities=["managed a team of 12", "budget ownership"],
        reason_for_leaving="Company restructuring",
    ),
    "raw_input": (
        "Renee was on our team from September 2019 to November 2023. She was "
        "a Software Engineer II, individual contributor -- she wasn't in a "
        "management role while she was here. Solid technical work though, "
        "good collaborator."
    ),
}

ALL_CASES = {
    "clean": clean,
    "date_mismatch": date_mismatch,
    "hedging_reference": hedging_reference,
    "title_inflation": title_inflation,
}
