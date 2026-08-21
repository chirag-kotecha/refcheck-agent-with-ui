"""
Streamlit UI for the Reference Check Analyzer API.

Lets a user build up a candidate + a list of references (choosing REF1
open-text or REF2 yes/no per reference, with the form adapting to that
choice), submit to the FastAPI service, then poll for and display the
result.

Run with:
    streamlit run streamlit_app.py
Requires the FastAPI service running separately -- set API_BASE_URL if
it's not on the default http://localhost:8000 (docker-compose sets this
automatically for the containerized setup, see docker-compose.yml).
"""

import os
import time

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
YES_NO_OPTIONS = ["yes", "no", "unsure"]

st.set_page_config(page_title="Reference Check Analyzer", layout="wide")
st.title("Reference Check Analyzer")
st.caption(f"API: {API_BASE_URL}")

if "references" not in st.session_state:
    st.session_state.references = []
if "candidate" not in st.session_state:
    st.session_state.candidate = None
if "check_id" not in st.session_state:
    st.session_state.check_id = None

# ---------------------------------------------------------------------
# Candidate details
# ---------------------------------------------------------------------
st.subheader("1. Candidate")
with st.form("candidate_form"):
    col1, col2 = st.columns(2)
    candidate_name = col1.text_input("Candidate name")
    role_applied_for = col2.text_input("Role applied for")

    st.markdown("**Claimed details**")
    c1, c2, c3 = st.columns(3)
    job_title = c1.text_input("Job title (claimed)")
    company = c2.text_input("Company (claimed)")
    start_date = c3.text_input("Start date (YYYY-MM)")
    c4, c5 = st.columns(2)
    end_date = c4.text_input("End date (YYYY-MM, blank if still employed)")
    reason_for_leaving = c5.text_input("Reason for leaving (optional)")
    responsibilities_raw = st.text_input("Responsibilities (comma-separated, optional)")

    if st.form_submit_button("Save candidate details"):
        if not candidate_name or not role_applied_for or not job_title or not company or not start_date:
            st.error("Candidate name, role, job title, company, and start date are required.")
        else:
            st.session_state.candidate = {
                "candidate_name": candidate_name,
                "role_applied_for": role_applied_for,
                "claimed_details": {
                    "job_title": job_title,
                    "company": company,
                    "start_date": start_date,
                    "end_date": end_date or None,
                    "reason_for_leaving": reason_for_leaving or None,
                    "responsibilities": [r.strip() for r in responsibilities_raw.split(",") if r.strip()],
                },
            }
            st.success("Saved.")

if st.session_state.candidate:
    st.info(f"Candidate ready: {st.session_state.candidate['candidate_name']}")

st.divider()

# ---------------------------------------------------------------------
# References -- form fields adapt to REF1 vs REF2
# ---------------------------------------------------------------------
st.subheader("2. References")

ref_type_label = st.radio(
    "Type for the next reference",
    options=["REF1 -- Open text (transcript / email)", "REF2 -- Yes/No verification form"],
    horizontal=True,
)
ref_type = "REF1" if ref_type_label.startswith("REF1") else "REF2"

with st.form("reference_form", clear_on_submit=True):
    r1, r2 = st.columns(2)
    reference_name = r1.text_input("Reference name")
    relationship = r2.text_input("Relationship (e.g. Former Manager)")

    raw_input = None
    yes_no_fields = None

    if ref_type == "REF1":
        raw_input = st.text_area("Transcript / email text", height=150)
    else:
        y1, y2, y3 = st.columns(3)
        confirmed_title = y1.selectbox("Confirmed title?", YES_NO_OPTIONS)
        confirmed_dates = y2.selectbox("Confirmed dates?", YES_NO_OPTIONS)
        confirmed_company = y3.selectbox("Confirmed company?", YES_NO_OPTIONS)
        y4, y5 = st.columns(2)
        would_rehire = y4.selectbox("Would rehire?", YES_NO_OPTIONS)
        performance_concerns = y5.selectbox("Performance concerns?", YES_NO_OPTIONS)
        additional_comments = st.text_area("Additional comments (optional)", height=100)
        yes_no_fields = {
            "confirmed_title": confirmed_title,
            "confirmed_dates": confirmed_dates,
            "confirmed_company": confirmed_company,
            "would_rehire": would_rehire,
            "performance_concerns": performance_concerns,
            "additional_comments": additional_comments or None,
        }

    if st.form_submit_button("Add reference"):
        if not reference_name or not relationship:
            st.error("Reference name and relationship are required.")
        elif ref_type == "REF1" and (not raw_input or len(raw_input.strip()) < 10):
            st.error("Transcript/email text is required (at least 10 characters).")
        else:
            ref = {"reference_name": reference_name, "relationship": relationship, "type": ref_type}
            if ref_type == "REF1":
                ref["raw_input"] = raw_input
            else:
                ref["yes_no_form"] = yes_no_fields
            st.session_state.references.append(ref)
            st.success(f"Added: {reference_name} ({ref_type})")

if st.session_state.references:
    st.markdown(f"**{len(st.session_state.references)} reference(s) added:**")
    for i, ref in enumerate(st.session_state.references):
        col1, col2 = st.columns([6, 1])
        col1.write(f"- {ref['reference_name']} ({ref['relationship']}) — {ref['type']}")
        if col2.button("Remove", key=f"remove_{i}"):
            st.session_state.references.pop(i)
            st.rerun()

st.divider()

# ---------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------
st.subheader("3. Submit")

callback_url = st.text_input(
    "Callback URL (optional -- the API will POST the result here when done, in addition to being pollable below)"
)

if st.button("Submit reference check", type="primary"):
    if not st.session_state.candidate:
        st.error("Save candidate details first.")
    elif not st.session_state.references:
        st.error("Add at least one reference first.")
    else:
        payload = {**st.session_state.candidate, "references": st.session_state.references}
        if callback_url:
            payload["callback_url"] = callback_url
        try:
            resp = requests.post(f"{API_BASE_URL}/api/v1/checks", json=payload, timeout=30)
            resp.raise_for_status()
            st.session_state.check_id = resp.json()["check_id"]
            st.success(f"Submitted. check_id = {st.session_state.check_id}")
        except Exception as e:
            st.error(f"Submission failed: {e}")

# ---------------------------------------------------------------------
# Poll for result
# ---------------------------------------------------------------------
if st.session_state.check_id:
    st.divider()
    st.subheader("4. Result")
    st.write(f"check_id: `{st.session_state.check_id}`")

    col1, col2 = st.columns([1, 4])
    manual_refresh = col1.button("Refresh status")
    auto_refresh = col2.checkbox("Auto-refresh every 3s until done")

    try:
        resp = requests.get(f"{API_BASE_URL}/api/v1/checks/{st.session_state.check_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.error(f"Could not fetch status: {e}")
        data = None

    if data:
        status = data["status"]
        if status == "queued":
            st.info("Queued...")
        elif status == "running":
            st.info("Running...")
        elif status == "failed":
            st.error(f"Failed: {data.get('error')}")
        elif status == "completed":
            result = data["result"]
            st.success("Completed")
            m1, m2 = st.columns(2)
            m1.metric("Overall confidence", f"{result['overall_confidence']:.1f}/100")
            m2.metric("Needs human review", str(result["overall_needs_review"]))

            for r in result["reference_results"]:
                with st.expander(
                    f"{r['reference_name']} ({r['relationship']}) — confidence {r['confidence_score']}"
                ):
                    st.write(f"Sentiment: {r['sentiment']}")
                    st.write(f"Needs review: {r['needs_human_review']}")
                    if r["discrepancies"]:
                        st.write("**Discrepancies:**")
                        for d in r["discrepancies"]:
                            st.write(
                                f"- [{d['severity']}] {d['field']}: "
                                f"claimed={d['claimed_value']!r} vs stated={d['stated_value']!r}"
                            )
                            if d.get("note"):
                                st.caption(d["note"])
                    if r["red_flags"]:
                        st.write("**Red flags:**")
                        for rf in r["red_flags"]:
                            st.write(f"- {rf}")
                    st.write("**Reference summary:**")
                    st.write(r["reference_summary"])

            if result.get("cross_reference_flags"):
                st.markdown("**Cross-reference flags** (references disagreeing with each other):")
                for f in result["cross_reference_flags"]:
                    st.write(f"- [{f['severity']}] {f['field']}: {f['description']}")

            st.markdown("**Overall summary:**")
            st.write(result["overall_summary"])

        if status in ("queued", "running") and (auto_refresh or manual_refresh):
            time.sleep(3)
            st.rerun()

if st.button("Start a new check"):
    st.session_state.references = []
    st.session_state.candidate = None
    st.session_state.check_id = None
    st.rerun()
