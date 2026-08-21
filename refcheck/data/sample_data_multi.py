"""
Candidate-level sample cases with multiple references each:
1. consistent_clean         -> both REF1 references agree -> overall_clear
2. cross_reference_conflict -> REF1 references disagree with EACH OTHER
3. mixed_single_ref_issue   -> one REF1 clean, another has its own discrepancy
4. yes_no_clean             -> both REF2 forms, all confirmed, no comments
5. yes_no_with_concerns     -> a REF2 form with a "no" answer + comments
6. mixed_reference_types    -> one REF1 + one REF2 for the same candidate
"""

from refcheck.schemas import ClaimedDetails, ReferenceInput, YesNoReferenceForm

consistent_clean = {
    "candidate_name": "Isabelle Duarte",
    "role_applied_for": "UX Designer",
    "claimed_details": ClaimedDetails(
        job_title="UX Designer", company="Foundry Studio",
        start_date="2021-06", end_date="2024-03",
        responsibilities=["user research", "design systems"],
        reason_for_leaving="Studio downsized",
    ),
    "references": [
        ReferenceInput(
            reference_name="Tom Reyes", relationship="Former Manager", type="REF1",
            raw_input=(
                "Isabelle was our UX Designer from June 2021 to March 2024, "
                "when we had to downsize the studio. She led our design "
                "system work and did great user research. Would rehire "
                "in a heartbeat."
            ),
        ),
        ReferenceInput(
            reference_name="Priya Shah", relationship="Peer Designer", type="REF1",
            raw_input=(
                "Yep, Isabelle and I worked together as designers from "
                "2021 to early 2024. She was fantastic to collaborate "
                "with, always thorough on research. Sad to see her leave "
                "when the studio downsized."
            ),
        ),
    ],
}

cross_reference_conflict = {
    "candidate_name": "Owen Callahan",
    "role_applied_for": "Sales Director",
    "claimed_details": ClaimedDetails(
        job_title="Sales Director", company="Vertex Building Supply",
        start_date="2020-04", end_date="2023-09",
        responsibilities=["managed regional sales team", "quota ownership"],
        reason_for_leaving="Seeking bigger opportunity",
    ),
    "references": [
        ReferenceInput(
            reference_name="Grace Liu", relationship="Former VP (skip-level)", type="REF1",
            raw_input=(
                "Owen was Sales Director here from 2020 to 2023. Top "
                "performer, consistently beat quota, great with the team. "
                "Strong hire, no hesitation recommending him."
            ),
        ),
        ReferenceInput(
            reference_name="Kevin Marsh", relationship="Direct Report", type="REF1",
            raw_input=(
                "I reported to Owen at Vertex. Honestly it was a rough "
                "experience -- he took credit for the team's numbers and "
                "was pretty dismissive in one-on-ones. Performance-wise "
                "for himself, sure, he hit his targets. But as a manager, "
                "weak. A couple of us were pretty unhappy."
            ),
        ),
    ],
}

mixed_single_ref_issue = {
    "candidate_name": "Fatima Al-Sayed",
    "role_applied_for": "Financial Analyst",
    "claimed_details": ClaimedDetails(
        job_title="Financial Analyst", company="Harborline Capital",
        start_date="2022-01", end_date="2024-01",
        responsibilities=["financial modeling", "quarterly reporting"],
        reason_for_leaving="Relocation",
    ),
    "references": [
        ReferenceInput(
            reference_name="David Okonkwo", relationship="Former Manager", type="REF1",
            raw_input=(
                "Fatima worked as a Financial Analyst for us, January "
                "2022 through January 2024. Excellent modeling work, "
                "very detail-oriented, left on good terms due to a "
                "relocation. Would rehire."
            ),
        ),
        ReferenceInput(
            reference_name="Lena Brooks", relationship="Peer Analyst", type="REF1",
            raw_input=(
                "I want to say Fatima joined sometime in mid-2022, not "
                "sure exactly. She was more of a Junior Analyst when she "
                "started I believe, handled some of the smaller reporting "
                "tasks. Fine to work with, no issues."
            ),
        ),
    ],
}

yes_no_clean = {
    "candidate_name": "Marcus Webb",
    "role_applied_for": "Operations Coordinator",
    "claimed_details": ClaimedDetails(
        job_title="Operations Coordinator", company="Brightline Logistics",
        start_date="2021-08", end_date="2023-12",
        responsibilities=["scheduling", "vendor coordination"],
        reason_for_leaving="Seeking new opportunity",
    ),
    "references": [
        ReferenceInput(
            reference_name="HR Dept, Brightline Logistics",
            relationship="Former Employer (HR-mediated verification)", type="REF2",
            yes_no_form=YesNoReferenceForm(
                confirmed_title="yes", confirmed_dates="yes", confirmed_company="yes",
                would_rehire="yes", performance_concerns="no", additional_comments=None,
            ),
        ),
        ReferenceInput(
            reference_name="Dana Fitch", relationship="Former Supervisor", type="REF2",
            yes_no_form=YesNoReferenceForm(
                confirmed_title="yes", confirmed_dates="yes", confirmed_company="yes",
                would_rehire="yes", performance_concerns="no", additional_comments=None,
            ),
        ),
    ],
}

yes_no_with_concerns = {
    "candidate_name": "Priya Chandran",
    "role_applied_for": "Customer Support Lead",
    "claimed_details": ClaimedDetails(
        job_title="Customer Support Lead", company="Nimbus Cloud Services",
        start_date="2022-03", end_date="2024-05",
        responsibilities=["team lead for support queue", "escalation handling"],
        reason_for_leaving="Company restructuring",
    ),
    "references": [
        ReferenceInput(
            reference_name="HR Dept, Nimbus Cloud Services",
            relationship="Former Employer (HR-mediated verification)", type="REF2",
            yes_no_form=YesNoReferenceForm(
                confirmed_title="no", confirmed_dates="yes", confirmed_company="yes",
                would_rehire="unsure", performance_concerns="yes",
                additional_comments=(
                    "Our records show this person was a Support Specialist, "
                    "not a Team Lead. There were also a couple of escalated "
                    "complaints about response times in their final months."
                ),
            ),
        ),
    ],
}

mixed_reference_types = {
    "candidate_name": "Aaron Kessler",
    "role_applied_for": "Warehouse Supervisor",
    "claimed_details": ClaimedDetails(
        job_title="Warehouse Supervisor", company="Redline Freight Co",
        start_date="2020-09", end_date="2023-10",
        responsibilities=["shift scheduling", "inventory audits"],
        reason_for_leaving="Relocated for family reasons",
    ),
    "references": [
        ReferenceInput(
            reference_name="Nora Islas", relationship="Former Manager", type="REF1",
            raw_input=(
                "Aaron supervised our warehouse floor from late 2020 until "
                "he relocated in October 2023. Reliable, good with the "
                "scheduling software, kept the audits on track. Would "
                "rehire without hesitation."
            ),
        ),
        ReferenceInput(
            reference_name="HR Dept, Redline Freight Co",
            relationship="Former Employer (HR-mediated verification)", type="REF2",
            yes_no_form=YesNoReferenceForm(
                confirmed_title="yes", confirmed_dates="yes", confirmed_company="yes",
                would_rehire="yes", performance_concerns="no", additional_comments=None,
            ),
        ),
    ],
}

ALL_MULTI_CASES = {
    "consistent_clean": consistent_clean,
    "cross_reference_conflict": cross_reference_conflict,
    "mixed_single_ref_issue": mixed_single_ref_issue,
    "yes_no_clean": yes_no_clean,
    "yes_no_with_concerns": yes_no_with_concerns,
    "mixed_reference_types": mixed_reference_types,
}
