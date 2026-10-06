from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

from core import repository as repo
from core.db import get_session, init_db
from core.diagram_types import DiagramKind
from core.generator import GeneratedDiagram
from core.llm import check_models
from core.orchestrator import handle_feedback, handle_generate
from core.renderer import render_svg
from core.schemas import DesignModel, FeedbackRequest, GenerateRequest

SEBI_EXAMPLE = {
    "prompt": (
        "I am working on a compliance monitoring solution which will pull in the latest "
        "circulars from SEBI and parse them. Once it is parsed into a table of clauses, "
        "you will need to extract the following information:\n"
        "1. The new compliance requirements proposed by the regulator\n"
        "2. Gap analysis with my existing compliance setup\n"
        "3. The impact of these new compliance requirements on my organization "
        "at an IT and operational level"
    ),
    "diagram_types": [
        "sequential",
        "component",
        "class",
        "activity",
        "deployment",
        "use_case",
    ],
}


def _run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _ensure_uid() -> str:
    if "uid" in st.session_state and st.session_state.uid:
        return st.session_state.uid

    qp = st.query_params.get("uid")
    if qp:
        st.session_state.uid = qp
        return qp

    # Try localStorage via streamlit-local-storage if available
    try:
        from streamlit_local_storage import LocalStorage

        storage = LocalStorage()
        stored = storage.getItem("uml_uid")
        if stored:
            st.session_state.uid = stored
            st.query_params["uid"] = stored
            return stored
        new_id = str(uuid.uuid4())
        storage.setItem("uml_uid", new_id)
        st.session_state.uid = new_id
        st.query_params["uid"] = new_id
        return new_id
    except Exception:
        new_id = str(uuid.uuid4())
        st.session_state.uid = new_id
        st.query_params["uid"] = new_id
        return new_id


def _init_state():
    init_db()
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None
    if "selected_version_id" not in st.session_state:
        st.session_state.selected_version_id = None
    if "results" not in st.session_state:
        st.session_state.results = {}
    if "json_mode" not in st.session_state:
        st.session_state.json_mode = False
    if "pending_placeholders" not in st.session_state:
        st.session_state.pending_placeholders = {}


def _show_svg(svg: Optional[str], height: int = 560):
    if not svg:
        st.info("No SVG available.")
        return
    components.html(
        f'<div style="overflow:auto;background:#fff;padding:8px;">{svg}</div>',
        height=height,
        scrolling=True,
    )


def _dget(d, key, default=None):
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _render_diagram_tab(d, uid: str):
    diagram_id = _dget(d, "id")
    version_id = _dget(d, "version_id")
    kind = _dget(d, "kind")
    plantuml = _dget(d, "plantuml") or ""
    svg = _dget(d, "svg")
    is_valid = bool(_dget(d, "is_valid"))
    error = _dget(d, "error")
    attempts = _dget(d, "attempts", 1)
    latency_ms = _dget(d, "latency_ms", 0)
    reused = bool(_dget(d, "reused_from_id") or _dget(d, "reused"))
    warnings = _dget(d, "warnings") or []

    cols = st.columns([1, 1, 1, 1, 1])
    cols[0].markdown("**valid**" if is_valid else "**invalid**")
    cols[1].markdown("**consistent**" if is_valid and not warnings else "")
    cols[2].caption(f"attempts {attempts}")
    cols[3].caption(f"{latency_ms} ms")
    if reused:
        cols[4].caption("reused")
    for w in warnings:
        st.warning(w)

    if is_valid and svg:
        _show_svg(svg)
    else:
        st.error(error or "Diagram failed validation")

    with st.expander("PlantUML code", expanded=False):
        st.code(plantuml, language="text")
        edited = st.text_area(
            "Edit & re-render",
            value=plantuml,
            key=f"edit_{diagram_id}",
            height=200,
        )
        if st.button("Re-render", key=f"rerender_{diagram_id}"):
            ok, new_svg, err = _run(render_svg(edited))
            if ok and new_svg:
                with get_session() as session:
                    diag = repo.get_diagram(session, diagram_id)
                    if diag:
                        diag.plantuml = edited
                        diag.svg = new_svg
                        diag.is_valid = True
                        diag.error = None
                        session.add(diag)
                        for t in repo.trajectories_for_diagram(session, diagram_id):
                            t.metrics = {**(t.metrics or {}), "manual_edit": True}
                            t.reward = 1.0
                            session.add(t)
                st.success("Re-rendered and saved.")
                st.rerun()
            else:
                st.error(err or "Render failed")

        c1, c2 = st.columns(2)
        c1.download_button(
            "Download .puml",
            data=plantuml.encode(),
            file_name=f"{kind}.puml",
            mime="text/plain",
            key=f"dl_puml_{diagram_id}",
        )
        if svg:
            c2.download_button(
                "Download .svg",
                data=svg.encode(),
                file_name=f"{kind}.svg",
                mime="image/svg+xml",
                key=f"dl_svg_{diagram_id}",
            )

    st.markdown("#### Feedback")
    rating = st.feedback("thumbs", key=f"fb_{diagram_id}")
    comment = st.text_input("Comment (optional)", key=f"fb_c_{diagram_id}")
    apply_rev = st.checkbox("Apply as revision", key=f"fb_a_{diagram_id}")
    if st.button("Submit feedback", key=f"fb_s_{diagram_id}"):
        if rating is None:
            st.warning("Select thumbs up or down first.")
        else:
            mapped = 1 if rating == 1 else -1
            result = _run(
                handle_feedback(
                    FeedbackRequest(
                        user_id=uid,
                        version_id=version_id,
                        diagram_id=diagram_id,
                        rating=mapped,
                        comment=comment or None,
                        apply_as_update=apply_rev,
                    )
                )
            )
            st.toast("Thanks, feedback saved")
            if result.get("generate"):
                st.session_state.conversation_id = result["generate"]["conversation_id"]
                st.session_state.selected_version_id = result["generate"]["version_id"]
                st.rerun()


def _render_design_model(raw: Optional[dict], version_id: int):
    if not raw:
        st.caption("No shared design model for this version (generated before it existed).")
        return
    model = DesignModel.model_validate(raw)
    with st.expander(f"Shared design model: {model.system_name}", expanded=False):
        if model.summary:
            st.write(model.summary)
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Actors**\n" + "\n".join(f"- {a.name}" for a in model.actors))
        c1.markdown(
            "**External systems**\n"
            + "\n".join(f"- {e.name}" for e in model.external_systems)
        )
        layers: dict[str, list[str]] = {}
        for c in model.components:
            layers.setdefault(c.layer or "Core", []).append(c.name)
        c2.markdown(
            "**Components**\n"
            + "\n".join(
                f"- *{layer}*: {', '.join(names)}" for layer, names in layers.items()
            )
        )
        c3.markdown(
            "**Data stores**\n"
            + "\n".join(f"- {d.name} ({d.technology})" for d in model.data_stores)
        )
        if model.main_flow:
            st.markdown("**Main flow**")
            st.markdown(
                "\n".join(
                    f"{s.step}. {s.source} → {s.target}: {s.message}"
                    for s in sorted(model.main_flow, key=lambda s: s.step)
                )
            )
        st.download_button(
            "Download design model (.json)",
            data=model.model_dump_json(indent=2).encode(),
            file_name="design_model.json",
            mime="application/json",
            key=f"dl_model_{version_id}",
        )


def _load_version_view(version_id: int, uid: str):
    with get_session() as session:
        version = repo.get_version(session, version_id)
        if version is None:
            st.warning("Version not found.")
            return
        prompt = version.prompt
        change_summary = version.change_summary
        design_raw = version.design_model
        diagrams = [
            {
                "id": d.id,
                "version_id": d.version_id,
                "kind": d.kind,
                "title": d.title,
                "plantuml": d.plantuml,
                "svg": d.svg,
                "is_valid": d.is_valid,
                "error": d.error,
                "attempts": d.attempts,
                "latency_ms": d.latency_ms,
                "reused_from_id": d.reused_from_id,
                "reused": d.reused_from_id is not None,
                "warnings": list(d.warnings or []),
            }
            for d in repo.list_diagrams(session, version_id)
        ]

    st.chat_message("user").write(prompt)
    with st.chat_message("assistant"):
        if change_summary:
            st.caption(f"Changes: {change_summary}")
        _render_design_model(design_raw, version_id)
        if not diagrams:
            st.info("No diagrams in this version.")
            return
        tabs = st.tabs([d["title"] or d["kind"] for d in diagrams])
        for tab, d in zip(tabs, diagrams):
            with tab:
                _render_diagram_tab(d, uid)


def main():
    st.set_page_config(page_title="UML Studio", layout="wide")
    _init_state()
    uid = _ensure_uid()
    with get_session() as session:
        repo.get_or_create_user(session, uid)

    models = st.cache_resource(check_models)()
    from core.config import get_settings

    settings = get_settings()

    with st.sidebar:
        st.title("UML Studio")
        st.caption(f"User `{uid[:8]}…`")
        if st.button("Copy full user id"):
            st.code(uid)
        if st.button("New design", type="primary"):
            st.session_state.conversation_id = None
            st.session_state.selected_version_id = None
            st.session_state.results = {}
            st.rerun()

        st.subheader("Conversations")
        with get_session() as session:
            convs = [
                {"id": c.id, "title": c.title}
                for c in repo.list_conversations(session, uid)
            ]
        for c in convs:
            label = f"#{c['id']} {c['title'][:40]}"
            if st.button(label, key=f"conv_{c['id']}"):
                st.session_state.conversation_id = c["id"]
                with get_session() as session:
                    latest = repo.latest_version(session, c["id"])
                    st.session_state.selected_version_id = (
                        latest.id if latest else None
                    )
                st.rerun()

        kind_options = [k.value for k in DiagramKind]
        selected_kinds = st.multiselect(
            "Diagram types",
            options=kind_options,
            default=["sequence", "component", "class", "activity", "deployment"],
        )
        mode = st.radio("Input mode", ["Chat", "JSON"], horizontal=True)
        st.session_state.json_mode = mode == "JSON"
        st.caption(f"gen: `{settings.gen_model}`")
        st.caption(f"fast: `{settings.fast_model}`")
        if models and not all(models.values()):
            inactive = [m for m, ok in models.items() if not ok]
            st.warning(f"Models not active on Groq: {', '.join(inactive)}")

    # Header
    cid = st.session_state.conversation_id
    if cid is None:
        st.header("New design")
        st.markdown(
            "Describe a software system. UML Studio generates PlantUML diagrams "
            "via Groq, validates them with Kroki, and learns from your feedback."
        )
        chips = st.columns(3)
        examples = [
            ("SEBI compliance", SEBI_EXAMPLE["prompt"], SEBI_EXAMPLE["diagram_types"]),
            (
                "Order checkout",
                "Design an e-commerce checkout with cart, payment gateway, inventory, and fraud checks.",
                ["sequence", "component", "state_machine"],
            ),
            (
                "Data pipeline",
                "Build a batch ETL pipeline: S3 ingest, Spark transform, warehouse load, and DQ alerts.",
                ["activity", "deployment", "component"],
            ),
        ]
        for col, (label, prompt, types) in zip(chips, examples):
            if col.button(label):
                st.session_state["prefill_prompt"] = prompt
                st.session_state["prefill_types"] = types
    else:
        with get_session() as session:
            versions = [
                {"id": v.id, "version_no": v.version_no}
                for v in repo.list_versions(session, cid)
            ]
            conv_title = next(
                (
                    c.title
                    for c in repo.list_conversations(session, uid)
                    if c.id == cid
                ),
                None,
            )
        st.header(conv_title or f"Conversation {cid}")
        if versions:
            labels = {f"v{v['version_no']}": v["id"] for v in versions}
            choice = st.selectbox(
                "Version",
                options=list(labels.keys()),
                index=len(labels) - 1,
            )
            st.session_state.selected_version_id = labels[choice]
            for v in versions:
                if v["id"] == st.session_state.selected_version_id:
                    _load_version_view(v["id"], uid)

    # Input
    prompt_text: Optional[str] = None
    diagram_types = selected_kinds
    if "prefill_types" in st.session_state:
        diagram_types = st.session_state.pop("prefill_types")

    if st.session_state.json_mode:
        default_json = json.dumps(SEBI_EXAMPLE, indent=2)
        raw = st.text_area("JSON request", value=default_json, height=280)
        if st.button("Generate", type="primary"):
            try:
                req = GenerateRequest.model_validate_json(raw)
                prompt_text = req.prompt
                diagram_types = req.diagram_types or selected_kinds
            except Exception as e:
                st.error(f"Invalid JSON: {e}")
    else:
        prefill = st.session_state.pop("prefill_prompt", "")
        if prefill:
            st.session_state["chat_prefill"] = prefill
        prompt_text = st.chat_input("Describe your software design...")
        if "chat_prefill" in st.session_state and not prompt_text:
            st.info("Example loaded — press send in the chat input (or paste it).")
            st.code(st.session_state["chat_prefill"])
            if st.button("Use example prompt"):
                prompt_text = st.session_state.pop("chat_prefill")

    if prompt_text:
        if not diagram_types:
            st.error("Select at least one diagram type.")
            st.stop()
        req = GenerateRequest(
            prompt=prompt_text,
            diagram_types=diagram_types,
            user_id=uid,
            conversation_id=st.session_state.conversation_id,
        )
        status = st.status(
            "Building shared design model, then generating diagrams…", expanded=True
        )
        placeholders = {k: status.empty() for k in diagram_types}

        def on_done(item: GeneratedDiagram):
            ph = placeholders.get(item.kind.value) or placeholders.get(
                next(iter(placeholders), "")
            )
            if ph is None:
                return
            if item.is_valid:
                ph.success(f"{item.kind.value}: {item.title} ({item.latency_ms} ms)")
            else:
                ph.error(f"{item.kind.value}: {item.error}")

        try:
            with st.spinner("Calling Groq + Kroki…"):
                resp = _run(handle_generate(req, on_done=on_done))
            status.update(label="Done", state="complete")
            if resp.unknown_types:
                st.warning(f"Unknown diagram types ignored: {resp.unknown_types}")
            st.session_state.conversation_id = resp.conversation_id
            st.session_state.selected_version_id = resp.version_id
            st.rerun()
        except Exception as e:
            status.update(label="Failed", state="error")
            st.exception(e)


if __name__ == "__main__":
    main()
