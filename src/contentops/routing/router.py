"""The one entry point: choose an account, choose a route, get a brief.

Why this exists
---------------
Before this module, "what should we make next" had two answers living in
different places — a hot list and a person's head — and neither one recorded
where the topic came from. The pipeline downstream could not tell them apart,
so it could not enforce anything about either.

So there is a single entrance with three explicit inputs:

``account_id``
    Which account's positioning governs this run. Never inferred from the
    topic, the platform or the route.

``route_mode``
    ``HOTSPOT_DISCOVERY`` or ``USER_TOPIC``. Never inferred. A caller that
    omits it gets ``ROUTE_SELECTION_REQUIRED`` and nothing else; the router
    will not guess what someone meant, because guessing here means silently
    doing a different job than the one asked for.

``input_payload``
    What the route needs. A topic for ``USER_TOPIC``; nothing for
    ``HOTSPOT_DISCOVERY``, which finds its own material.

The route never changes on its own. A run that started as a hot-list search
resumes as a hot-list search even when a source is down, because "the source
was down" is a reason to report a failure, not a reason to go and make
something else. Changing the route requires starting a new run.

Where the state lives
---------------------
In the store, per account, with an event trail. The state machine in
:mod:`contentops.routing.models` is the only thing that moves a run, and it
has no force path.

What this module does not do
----------------------------
It does not approve anything for production, and it does not publish. The
``APPROVED_FOR_PRODUCTION`` state means "a person confirmed this brief may
enter the pipeline". The copy review, downstream and untouched, is still what
stands between a script and a render.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import brief as brief_module
from . import hotspot_route, user_topic_route
from .account_profile import (
    AccountProfile,
    load_profile,
    list_account_slugs,
    profile_video_capable,
    target_pipeline_for,
)
from ..hotspots.query_planner import plan_is_current
from ..hotspots.storage import RouterStore
from .models import (
    ACCOUNT_DNA_MISSING,
    ACCOUNT_REQUIRED,
    APPROVED_FOR_PRODUCTION,
    AWAITING_HUMAN_APPROVAL,
    BLOCKED,
    BRIEF_READY,
    CANDIDATES_READY,
    ContentIntent,
    EVIDENCE_REQUIRED,
    INPUT_REQUIRED,
    OUT_OF_PROFILE_REVIEW_REQUIRED,
    ROUTE_SELECTION_REQUIRED,
    ROUTE_MODES,
    RouteContext,
    SEARCH_PLAN_READY,
    TOPIC_SELECTED,
    RoutingError,
    assert_transition,
    digest,
    utcnow,
)
from .user_topic_route import UserTopicInput

#: The default freshness window for a hot-list run, in hours.
DEFAULT_FRESHNESS_HOURS = 72


@dataclass
class RunResult:
    """What a router call produced. One shape for every command."""

    run_id: str
    account_id: str
    route_mode: str
    state: str
    detail: Dict[str, Any]
    ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "account_id": self.account_id,
            "route_mode": self.route_mode,
            "state": self.state,
            "ok": self.ok,
            **self.detail,
        }


class ContentRouter:
    """Routes content into briefs for one repository's accounts."""

    def __init__(self, root: Path, *, store: Optional[RouterStore] = None,
                 adapters: Optional[Dict[str, Any]] = None,
                 trendradar_db: Optional[str] = None,
                 projects_root: Optional[Path] = None,
                 timeout: float = 12.0) -> None:
        self.root = Path(root)
        self.store = store if store is not None else RouterStore(self.root)
        self.adapters = adapters
        self.trendradar_db = trendradar_db
        #: Where a materialised project is created. The acceptance run points
        #: this away from the repository's own ``projects/``.
        self.projects_root = (Path(projects_root) if projects_root is not None
                              else self.root / "projects")
        self.timeout = timeout

    # -- accounts -----------------------------------------------------------

    def accounts(self) -> List[Dict[str, Any]]:
        """Every account, whether or not its DNA resolves.

        An account whose DNA is unusable is still listed, with the reason it
        cannot be used. Hiding it would leave the owner wondering where their
        account went.
        """
        entries: List[Dict[str, Any]] = []
        for slug in list_account_slugs(self.root):
            try:
                profile = load_profile(self.root, slug)
            except RoutingError as exc:
                entries.append({
                    "account_id": slug,
                    "usable": False,
                    "code": exc.code,
                    "reason": exc.detail,
                })
                continue
            entries.append({
                "account_id": profile.account_id,
                "usable": True,
                "platform": profile.platform,
                "positioning": profile.positioning,
                "profile_version": profile.profile_version,
                "profile_source": profile.profile_source,
                "pillars": list(profile.pillar_names()),
                "sources": list(profile.source_allowlist),
                "video_capable": profile_video_capable(profile),
                "target_pipeline": target_pipeline_for(profile),
                "keywords_positive": len(profile.keywords_positive),
                "keywords_negative": len(profile.keywords_negative),
            })
        return entries

    def profile(self, account_id: str) -> AccountProfile:
        """Resolve an account, with the failures named."""
        if not account_id:
            raise RoutingError(ACCOUNT_REQUIRED, "no account was named")
        try:
            return load_profile(self.root, account_id)
        except RoutingError as exc:
            if exc.code == "ACCOUNT_DNA_MISSING":
                raise RoutingError(ACCOUNT_DNA_MISSING, exc.detail) from None
            raise

    # -- start --------------------------------------------------------------

    def start(self, account_id: str, route_mode: Optional[str],
              payload: Optional[UserTopicInput] = None, *,
              pillar: Optional[str] = None,
              freshness_hours: int = DEFAULT_FRESHNESS_HOURS,
              per_source_limit: int = 30,
              accept_off_profile: bool = False,
              override_note: str = "",
              selected_by: str = "",
              fetch_evidence: bool = False,
              collect: bool = True) -> RunResult:
        """Begin a run. The route must be named explicitly."""
        profile = self.profile(account_id)
        if not route_mode:
            raise RoutingError(
                ROUTE_SELECTION_REQUIRED,
                "no route was named; choose HOTSPOT_DISCOVERY to look for a topic "
                "or USER_TOPIC to supply one. The router does not choose for you.")
        if route_mode not in ROUTE_MODES:
            raise RoutingError(
                "ROUTE_SELECTION_REQUIRED",
                f"route {route_mode!r} is not one of {list(ROUTE_MODES)}")
        self._check_approval_policy(profile)

        if route_mode == "HOTSPOT_DISCOVERY":
            return self._start_hotspot(profile, pillar=pillar,
                                       freshness_hours=freshness_hours,
                                       per_source_limit=per_source_limit,
                                       collect=collect)
        return self._start_user_topic(profile, payload or UserTopicInput(topic=""),
                                      accept_off_profile=accept_off_profile,
                                      override_note=override_note,
                                      selected_by=selected_by,
                                      fetch_evidence=fetch_evidence)

    def _check_approval_policy(self, profile: AccountProfile) -> None:
        """The account may not declare itself exempt from the human gates."""
        policy = profile.approval_policy
        if not policy:
            return
        for key in ("topic_selection_required", "brief_approval_required"):
            if key in policy and policy[key] is not True:
                raise RoutingError(
                    "ACCOUNT_DNA_MALFORMED",
                    f"{profile.account_id} declares approval_policy.{key}=false; the "
                    f"router always requires a person to select the topic and to "
                    f"approve the brief, and an account cannot exempt itself")

    def _start_hotspot(self, profile: AccountProfile, *, pillar: Optional[str],
                       freshness_hours: int, per_source_limit: int,
                       collect: bool) -> RunResult:
        run_id = self._new_run_id(profile.account_id, "HOTSPOT_DISCOVERY")
        plan = hotspot_route.make_plan(profile, pillar=pillar,
                                       freshness_hours=freshness_hours,
                                       per_source_limit=per_source_limit)
        self.store.save_run(run_id, account_id=profile.account_id,
                             profile_version=profile.profile_version,
                             route_mode="HOTSPOT_DISCOVERY",
                             state=SEARCH_PLAN_READY, plan=plan)
        self.store.record_event(run_id, profile.account_id, SEARCH_PLAN_READY,
                                plan.get("summary", ""))
        if not collect:
            return RunResult(run_id, profile.account_id, "HOTSPOT_DISCOVERY",
                             SEARCH_PLAN_READY,
                             {"plan": plan, "message": "plan built; collection not run"})

        result = hotspot_route.collect(
            profile, plan, adapters=self.adapters,
            trendradar_db=self.trendradar_db, timeout=self.timeout,
            prior_appearances=lambda title: self.store.title_appearances(
                profile.account_id, title))
        self.store.save_candidates(run_id, account_id=profile.account_id,
                                   profile_version=profile.profile_version,
                                   candidates=result.candidates)
        self.store.update_run_state(run_id, CANDIDATES_READY)
        self.store.record_event(run_id, profile.account_id, CANDIDATES_READY,
                                f"{len(result.candidates)} candidate(s) from "
                                f"{len(result.fetch_results)} source(s)")
        return RunResult(run_id, profile.account_id, "HOTSPOT_DISCOVERY",
                         CANDIDATES_READY,
                         {"plan": plan, "collection": result.to_dict(),
                          "candidates": result.candidates})

    def _start_user_topic(self, profile: AccountProfile, payload: UserTopicInput, *,
                          accept_off_profile: bool, override_note: str,
                          selected_by: str,
                          fetch_evidence: bool = False,
                          run_id: Optional[str] = None) -> RunResult:
        if payload.is_empty():
            raise RoutingError(INPUT_REQUIRED,
                               "a user topic needs at least a topic, a link, a "
                               "document or a draft")
        failures = user_topic_route.validate_references(payload.urls)
        if failures:
            raise RoutingError("INPUT_INVALID", "; ".join(failures))

        if run_id is None:
            run_id = self._new_run_id(profile.account_id, "USER_TOPIC")
        self.store.save_run(run_id, account_id=profile.account_id,
                             profile_version=profile.profile_version,
                             route_mode="USER_TOPIC", state=INPUT_REQUIRED,
                             plan={"input": payload.to_dict()})
        self.store.record_event(run_id, profile.account_id, INPUT_REQUIRED,
                                payload.topic[:200])

        alignment = user_topic_route.evaluate(profile, payload)
        if alignment["alignment"] == "OFF_POSITIONING" and not accept_off_profile:
            self.store.update_run_state(run_id, OUT_OF_PROFILE_REVIEW_REQUIRED)
            self.store.record_event(run_id, profile.account_id,
                                    OUT_OF_PROFILE_REVIEW_REQUIRED,
                                    alignment["detail"])
            return RunResult(
                run_id, profile.account_id, "USER_TOPIC",
                OUT_OF_PROFILE_REVIEW_REQUIRED,
                {"alignment": alignment, "ok": False,
                 "message": "the topic does not match the account's declared "
                            "positioning. Change the topic, or approve the "
                            "exception explicitly with --accept-off-profile."},
                ok=False)

        override = None
        if alignment["alignment"] == "OFF_POSITIONING":
            override = {
                "accepted_by": selected_by or "unnamed",
                "accepted_at": utcnow(),
                "note": override_note or "",
                "reason": alignment["detail"],
            }

        intent, package = self._build_user_topic_brief(
            profile, payload, alignment=alignment, override=override,
            selected_by=selected_by, fetch_evidence=fetch_evidence)
        self._write_brief(run_id, package)
        self.store.save_run(run_id, account_id=profile.account_id,
                            profile_version=profile.profile_version,
                            route_mode="USER_TOPIC", state=AWAITING_HUMAN_APPROVAL,
                            intent=intent.to_dict())
        self.store.record_event(run_id, profile.account_id, AWAITING_HUMAN_APPROVAL,
                                intent.topic[:200])
        return RunResult(run_id, profile.account_id, "USER_TOPIC",
                         AWAITING_HUMAN_APPROVAL,
                         {"intent": intent.to_dict(), "alignment": alignment,
                          "brief": str(self._brief_path(run_id))})

    # -- selection ----------------------------------------------------------

    def select(self, account_id: str, run_id: str, candidate_id: str, *,
               selected_by: str) -> RunResult:
        """A person chooses one candidate. This step cannot be skipped."""
        profile = self.profile(account_id)
        run = self.store.get_run(run_id)
        if run is None:
            raise RoutingError("RUN_NOT_FOUND", f"no run {run_id!r}")
        if str(run.get("account_id")) != profile.account_id:
            raise RoutingError("ACCOUNT_MISMATCH",
                               f"run {run_id} belongs to account "
                               f"{run.get('account_id')!r}, not {profile.account_id!r}")
        if str(run.get("route_mode")) != "HOTSPOT_DISCOVERY":
            raise RoutingError(
                "ROUTE_MISMATCH",
                f"run {run_id} is a {run.get('route_mode')} run; a candidate can "
                f"only be selected in a HOTSPOT_DISCOVERY run")
        if str(run.get("state")) != CANDIDATES_READY:
            raise RoutingError(
                "ILLEGAL_TRANSITION",
                f"run {run_id} is {run.get('state')!r}; a candidate can only be "
                f"chosen from {CANDIDATES_READY!r}")

        candidate = self.store.get_candidate(profile.account_id, candidate_id)
        if candidate is None:
            raise RoutingError("CANDIDATE_NOT_FOUND",
                               f"no candidate {candidate_id!r} in this account's pool")
        if not selected_by.strip():
            raise RoutingError("SELECTOR_REQUIRED",
                               "a choice needs a name: who picked this topic")

        assert_transition(CANDIDATES_READY, TOPIC_SELECTED)
        self.store.set_candidate_status(profile.account_id, candidate_id,
                                        "selected", run_id=run_id)
        self.store.record_event(run_id, profile.account_id, TOPIC_SELECTED,
                                f"{candidate_id} by {selected_by}")

        intent, package = self._build_hotspot_brief(profile, candidate,
                                                     selected_by=selected_by)
        self._write_brief(run_id, package)
        self.store.save_run(run_id, account_id=profile.account_id,
                            profile_version=profile.profile_version,
                            route_mode="HOTSPOT_DISCOVERY",
                            state=AWAITING_HUMAN_APPROVAL, intent=intent.to_dict())
        self.store.record_event(run_id, profile.account_id, AWAITING_HUMAN_APPROVAL,
                                intent.topic[:200])
        return RunResult(run_id, profile.account_id, "HOTSPOT_DISCOVERY",
                         AWAITING_HUMAN_APPROVAL,
                         {"intent": intent.to_dict(), "selected": candidate_id,
                          "brief": str(self._brief_path(run_id))})

    # -- approval -----------------------------------------------------------

    def approve(self, account_id: str, run_id: str, *, reviewer: str,
                note: str = "", project_slug: Optional[str] = None,
                confirmed: bool = False, actor_kind: str = "human",
                allow_automation: bool = False) -> RunResult:
        """A person confirms the brief may enter the pipeline.

        Three things are required and none of them can be inferred:

        - ``confirmed`` — the caller has to say so. A running collector never
          reaches this method with it set, so collection cannot approve itself.
        - ``reviewer`` — a name, recorded with the time and the digest of what
          was approved.
        - ``actor_kind`` — ``human`` or ``automation``. An automation approval
          is refused unless the caller also passes ``allow_automation``, which
          exists so the acceptance harness can exercise the path in a sandbox
          and so that no production caller can do it by accident.
        """
        profile = self.profile(account_id)
        run = self.store.get_run(run_id)
        if run is None:
            raise RoutingError("RUN_NOT_FOUND", f"no run {run_id!r}")
        if str(run.get("account_id")) != profile.account_id:
            raise RoutingError("ACCOUNT_MISMATCH",
                               f"run {run_id} belongs to another account")
        if str(run.get("state")) != AWAITING_HUMAN_APPROVAL:
            raise RoutingError(
                "ILLEGAL_TRANSITION",
                f"run {run_id} is {run.get('state')!r}; a brief may only be approved "
                f"from {AWAITING_HUMAN_APPROVAL!r}")
        if not reviewer.strip():
            raise RoutingError("REVIEWER_REQUIRED", "an approval needs a named reviewer")
        if actor_kind not in ("human", "automation"):
            raise RoutingError("ACTOR_KIND_INVALID",
                               "an approval is either 'human' or 'automation'")
        if actor_kind == "automation" and not allow_automation:
            raise RoutingError(
                "AUTOMATION_APPROVAL_REFUSED",
                "an automation may not approve a brief; only a person can, and the "
                "acceptance harness must opt in explicitly")
        if not confirmed:
            raise RoutingError(
                "CONFIRMATION_REQUIRED",
                "an approval has to be confirmed explicitly; nothing reaches "
                "production without a person saying so")

        package = self.read_brief(run_id)
        if package is None:
            raise RoutingError("BRIEF_MISSING",
                               f"run {run_id} has no brief to approve")
        approved_digest = brief_module.content_digest(package)

        assert_transition(AWAITING_HUMAN_APPROVAL, APPROVED_FOR_PRODUCTION)
        intent_payload = run.get("intent_json")
        intent = ContentIntent.from_dict(json.loads(intent_payload)) \
            if intent_payload else None
        if intent is not None:
            intent.approval_status = "approved"
            intent.brief_status = "approved"
            intent.route_context.detail["approval"] = {
                "reviewer": reviewer.strip(),
                "actor_kind": actor_kind,
                "approved_at": utcnow(),
                "note": note.strip(),
                "content_digest": approved_digest,
            }
        self.store.save_run(run_id, account_id=profile.account_id,
                            profile_version=profile.profile_version,
                            route_mode=str(run.get("route_mode")),
                            state=APPROVED_FOR_PRODUCTION,
                            plan=json.loads(run["plan_json"]) if run.get("plan_json") else None,
                            intent=intent.to_dict() if intent is not None else None)
        self.store.record_event(run_id, profile.account_id, APPROVED_FOR_PRODUCTION,
                                f"approved by {reviewer} ({actor_kind}) "
                                f"digest {approved_digest[:12]}")

        # The brief is the document the pipeline reads, so the approval is
        # written back into it before it is handed on.
        if intent is not None:
            package = self.read_brief(run_id)
            if package is not None:
                self._write_brief(run_id, brief_module.record_approval(package, intent))

        detail: Dict[str, Any] = {"reviewer": reviewer.strip(), "note": note.strip(),
                                  "actor_kind": actor_kind,
                                  "content_digest": approved_digest,
                                  "approved_at": utcnow()}
        if project_slug:
            detail["project"] = str(self.materialize_project(profile, run_id,
                                                              intent, project_slug))
        return RunResult(run_id, profile.account_id, str(run.get("route_mode")),
                         APPROVED_FOR_PRODUCTION, detail)

    def verify_approval(self, run_id: str) -> Dict[str, Any]:
        """Whether the approval on a run still applies to the brief on disk.

        An approval is given for a piece of content, not for a run id. If the
        brief changed after it was approved — a different topic, a different
        candidate, a revised profile — the digest no longer matches and the
        approval is stale, which means the content has to be reviewed again.
        """
        run = self.store.get_run(run_id)
        if run is None:
            raise RoutingError("RUN_NOT_FOUND", f"no run {run_id!r}")
        recorded = {}
        intent_payload = run.get("intent_json")
        if intent_payload:
            try:
                recorded = ((json.loads(intent_payload).get("route_context") or {})
                            .get("detail") or {}).get("approval") or {}
            except (TypeError, ValueError):
                recorded = {}
        approved = str(recorded.get("content_digest") or "")
        package = self.read_brief(run_id)
        if str(run.get("state")) != APPROVED_FOR_PRODUCTION:
            return {"ok": False, "reason": "NOT_APPROVED",
                    "detail": f"the run is {run.get('state')!r}", "approval": recorded}
        if not approved:
            return {"ok": False, "reason": "APPROVAL_UNBOUND",
                    "detail": "the approval records no content digest, so it cannot "
                              "be tied to what was reviewed",
                    "approval": recorded}
        if package is None:
            return {"ok": False, "reason": "BRIEF_MISSING",
                    "detail": "the approved brief is not on disk", "approval": recorded}
        current = brief_module.content_digest(package)
        if current != approved:
            return {"ok": False, "reason": "APPROVAL_STALE",
                    "detail": f"the brief changed after approval (approved "
                              f"{approved[:12]}, now {current[:12]}); review it again",
                    "approval": recorded, "current_digest": current}
        return {"ok": True, "reason": "APPROVED", "content_digest": current,
                "approval": recorded}

    def materialize_project(self, profile: AccountProfile, run_id: str,
                            intent: Optional[ContentIntent],
                            project_slug: str) -> Path:
        """Create the project the brief belongs to, and put the brief in it.

        The project is created with the repository's own scaffolder, so the
        layout, the ``project.yaml`` and the directory set are the ones the
        pipeline already knows.
        """
        verdict = self.verify_approval(run_id)
        if not verdict["ok"]:
            raise RoutingError(
                "APPROVAL_NOT_VALID",
                f"the brief may not enter the pipeline: {verdict['detail']}")
        script_root = Path(__file__).resolve().parents[3] / "scripts"
        if str(script_root) not in sys.path:
            sys.path.insert(0, str(script_root))
        from new_project import create_project

        path = create_project(self.root, project_slug,
                              title=intent.topic if intent else project_slug,
                              account_slug=profile.account_id,
                              projects_dir=self.projects_root)
        package = self.read_brief(run_id)
        if package is not None:
            brief_module.write_brief_package(path, package)
        return path

    # -- reads --------------------------------------------------------------

    def candidates(self, account_id: str, *, run_id: Optional[str] = None
                   ) -> List[Dict[str, Any]]:
        profile = self.profile(account_id)
        return self.store.list_candidates(profile.account_id, run_id=run_id)

    def status(self, account_id: str, run_id: str) -> RunResult:
        profile = self.profile(account_id)
        run = self.store.get_run(run_id)
        if run is None:
            raise RoutingError("RUN_NOT_FOUND", f"no run {run_id!r}")
        if str(run.get("account_id")) != profile.account_id:
            raise RoutingError("ACCOUNT_MISMATCH", f"run {run_id} belongs to another account")
        events = self.store.list_events(run_id)
        return RunResult(run_id, profile.account_id, str(run.get("route_mode")),
                         str(run.get("state")),
                         {"run": {key: value for key, value in run.items()
                                  if key not in ("plan_json", "intent_json")},
                          "plan": json.loads(run["plan_json"]) if run.get("plan_json") else None,
                          "intent": json.loads(run["intent_json"]) if run.get("intent_json") else None,
                          "events": events,
                          "next": self.next_action(str(run.get("state")))})

    def _plan_currency(self, run: Dict[str, Any], profile: AccountProfile
                       ) -> Dict[str, Any]:
        """Whether the run's plan still describes the account as it is now.

        A run keeps the profile version it searched against, so an account
        whose profile has been revised since leaves the run's plan visibly
        behind. The run is not invalidated — it recorded what it actually did —
        but it is no longer what the account would search today.
        """
        plan = None
        if run.get("plan_json"):
            try:
                plan = json.loads(run["plan_json"])
            except (TypeError, ValueError):
                plan = None
        if not isinstance(plan, dict) or not plan.get("plan_id"):
            return {"current": False, "reason": "the run recorded no search plan"}
        current, reason = plan_is_current(plan, profile)
        return {"current": current, "reason": reason,
                "plan_profile_version": plan.get("account_profile_version"),
                "account_profile_version": profile.profile_version}

    def next_action(self, state: str) -> str:
        """What a person has to do next, in one sentence."""
        return {
            SEARCH_PLAN_READY: "run the collection to produce candidates",
            CANDIDATES_READY: "choose one candidate: content route select --candidate <id>",
            TOPIC_SELECTED: "the brief is being written",
            OUT_OF_PROFILE_REVIEW_REQUIRED:
                "change the topic, or approve the exception: "
                "content route start --mode topic --accept-off-profile --note \"...\"",
            EVIDENCE_REQUIRED: "collect or declare the evidence the topic needs",
            BRIEF_READY: "approve the brief: content route approve --reviewer <name> --confirm",
            AWAITING_HUMAN_APPROVAL:
                "approve the brief: content route approve --reviewer <name> --confirm",
            APPROVED_FOR_PRODUCTION: "the brief may enter the pipeline",
            BLOCKED: "this run stopped; start a new one",
            ACCOUNT_REQUIRED: "choose an account",
            ACCOUNT_DNA_MISSING: "the account has no usable DNA",
            ROUTE_SELECTION_REQUIRED: "choose a route: hotspot or topic",
            INPUT_REQUIRED: "supply a topic, a link, a document or a draft",
        }.get(state, "unknown state")

    def resume(self, account_id: str, run_id: str, *,
               accept_off_profile: bool = False,
               override_note: str = "") -> RunResult:
        """Continue a run, in the route it started in.

        The route is read from the run, never from the caller. A run that
        started as a hot-list search does not become a topic run because the
        hot list was empty.
        """
        profile = self.profile(account_id)
        run = self.store.get_run(run_id)
        if run is None:
            raise RoutingError("RUN_NOT_FOUND", f"no run {run_id!r}")
        if str(run.get("account_id")) != profile.account_id:
            raise RoutingError("ACCOUNT_MISMATCH", f"run {run_id} belongs to another account")
        route_mode = str(run.get("route_mode"))
        state = str(run.get("state"))

        if route_mode == "HOTSPOT_DISCOVERY":
            if state == CANDIDATES_READY:
                pool = self.store.list_candidates(profile.account_id, run_id=run_id)
                return RunResult(run_id, profile.account_id, route_mode, state,
                                 {"candidates": pool,
                                  "plan_currency": self._plan_currency(run, profile),
                                  "next": self.next_action(state)})
            return RunResult(run_id, profile.account_id, route_mode, state,
                             {"run": {key: value for key, value in run.items()
                                      if key not in ("plan_json", "intent_json")},
                              "plan_currency": self._plan_currency(run, profile),
                              "next": self.next_action(state)})

        if route_mode == "USER_TOPIC":
            if state == OUT_OF_PROFILE_REVIEW_REQUIRED and accept_off_profile:
                payload = self._recover_payload(run_id)
                if payload is None:
                    raise RoutingError(
                        "INPUT_REQUIRED",
                        f"run {run_id} is waiting on a topic the store no longer "
                        f"holds; start a new run with the topic again")
                return self._start_user_topic(
                    profile, payload, accept_off_profile=True,
                    override_note=override_note, selected_by="resume",
                    run_id=run_id)
            return RunResult(run_id, profile.account_id, route_mode, state,
                             {"run": {key: value for key, value in run.items()
                                      if key not in ("plan_json", "intent_json")},
                              "next": self.next_action(state)})

        raise RoutingError("ROUTE_SELECTION_REQUIRED",
                           f"run {run_id} names an unknown route {route_mode!r}")

    # -- internals ----------------------------------------------------------

    def _new_run_id(self, account_id: str, route_mode: str) -> str:
        seed = f"{account_id}|{route_mode}|{utcnow()}|{digest(uuid_marker())}"
        return f"RUN-{utcnow()[:10].replace('-', '')}-{digest(seed)[:8].upper()}"

    def _brief_path(self, run_id: str) -> Path:
        return self.store.home / "runs" / run_id / brief_module.BRIEF_DIR / brief_module.BRIEF_FILE

    def brief_path(self, run_id: str) -> Path:
        """Where a run's brief package is written."""
        return self._brief_path(run_id)

    def _write_brief(self, run_id: str, package: Dict[str, Any]) -> Path:
        failures = brief_module.validate_brief_package(package)
        if failures:
            raise RoutingError("BRIEF_INVALID",
                               "the brief would not pass the repository's contracts: "
                               + "; ".join(failures))
        return brief_module.write_brief_package(
            self.store.home / "runs" / run_id, package)

    def read_brief(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = self._brief_path(run_id)
        if not path.is_file():
            return None
        return brief_module.read_brief_package(path)

    def _recover_payload(self, run_id: str) -> Optional[UserTopicInput]:
        """The topic a waiting run was given.

        A run that stopped for review still holds the topic it was given, in
        its own record. Recovering it from there is what lets the owner
        approve the exception instead of typing the topic a second time.
        """
        run = self.store.get_run(run_id)
        if run is not None and run.get("plan_json"):
            try:
                recorded = (json.loads(run["plan_json"]) or {}).get("input") or {}
            except (TypeError, ValueError):
                recorded = {}
            if recorded.get("topic"):
                return UserTopicInput(
                    topic=str(recorded.get("topic") or ""),
                    urls=list(recorded.get("urls") or []),
                    local_paths=list(recorded.get("local_paths") or []),
                    notes=str(recorded.get("notes") or ""),
                )
        package = self.read_brief(run_id)
        if package is None:
            return None
        alignment = (package.get("intent") or {}).get("profile_alignment") or {}
        recorded = alignment.get("input") or {}
        return UserTopicInput(
            topic=str(recorded.get("topic") or ""),
            urls=list(recorded.get("urls") or []),
            local_paths=list(recorded.get("local_paths") or []),
            notes=str(recorded.get("notes") or ""),
        )

    def _build_hotspot_brief(self, profile: AccountProfile, candidate: Dict[str, Any],
                             *, selected_by: str) -> Tuple[ContentIntent, Dict[str, Any]]:
        topic = str(candidate.get("title") or "")
        components = (candidate.get("relevance") or {}).get("components") or {}
        # The alignment reads the same text the relevance gate read, so the
        # two judgements cannot disagree about the same candidate.
        alignment = brief_module.alignment_for(
            profile, f"{topic} {candidate.get('snippet') or ''}")
        trust = {"primary_artifact": "HIGH", "reported_not_verified": "MEDIUM"}.get(
            str(candidate.get("verification_status")), "LOW")
        decision = "ACCEPT"
        positioning = alignment["alignment"]
        if positioning == "OFF_POSITIONING":
            positioning = "OFF_POSITIONING"
            decision = "EXPERIMENT"

        candidate_doc = brief_module.candidate_document(
            candidate_id=str(candidate.get("candidate_id")),
            title=topic,
            thesis=_thesis(profile, candidate, positioning),
            audience_segment=_audience_segment(profile, topic),
            decision=decision,
            positioning_alignment=positioning,
            trust_level=trust,
            components=components)
        forecast = brief_module.forecast_document(
            topic_id=str(candidate.get("candidate_id")),
            profile=profile,
            verification_status=str(candidate.get("verification_status")),
            has_primary_source=bool(candidate.get("url")),
            assessment_basis=(
                f"The candidate came from {candidate.get('source_id')} and was chosen "
                f"by {selected_by}. The forecast names the evidence this episode "
                f"will need, before any of it is gathered."))
        intent = ContentIntent(
            account_id=profile.account_id,
            account_profile_version=profile.profile_version,
            route_mode="HOTSPOT_DISCOVERY",
            topic=topic,
            content_angle=None,
            source_artifact_refs=[str(candidate.get("url") or "")],
            evidence_status="verification_required",
            approval_status="pending",
            target_pipeline=target_pipeline_for(profile),
            brief_status="draft",
            route_context=RouteContext(
                mode="HOTSPOT_DISCOVERY",
                search_plan_id=str(candidate.get("plan_id") or ""),
                candidate_id=str(candidate.get("candidate_id")),
                topic_origin="HOTSPOT_SELECTION",
                user_input=None,
                selected_at=utcnow(),
                selected_by=selected_by,
                detail={"source_id": candidate.get("source_id"),
                        "source_rank": candidate.get("source_rank"),
                        "published_at": candidate.get("published_at"),
                        "collected_at": candidate.get("collected_at"),
                        "relevance": candidate.get("relevance"),
                        "verification_status": candidate.get("verification_status"),
                        "reasons_for": candidate.get("reasons_for"),
                        "reasons_against": candidate.get("reasons_against")},
            ),
            profile=profile.summary(),
            evidence=[{"kind": "authoritative_source",
                       "url": candidate.get("url"),
                       "source_id": candidate.get("source_id"),
                       "status": candidate.get("verification_status")}],
            profile_alignment=alignment,
        )
        package = brief_module.build_brief_package(
            intent=intent, profile=profile, candidate=candidate_doc,
            forecast=forecast,
            extra={"selection": {"candidate_id": candidate.get("candidate_id"),
                                 "selected_by": selected_by,
                                 "selected_at": utcnow(),
                                 "source_id": candidate.get("source_id")}})
        return intent, package

    def _build_user_topic_brief(self, profile: AccountProfile, payload: UserTopicInput, *,
                                alignment: Dict[str, Any],
                                override: Optional[Dict[str, Any]],
                                selected_by: str,
                                fetch_evidence: bool = False
                                ) -> Tuple[ContentIntent, Dict[str, Any]]:
        topic = payload.topic.strip()
        scoring = brief_module.topic_components(
            profile, topic=topic, snippet=payload.notes,
            url=payload.urls[0] if payload.urls else "",
            distinct_sources=max(1, len(payload.urls)))
        components = scoring["components"]
        has_primary = any(_is_primary(url) for url in payload.urls)
        verification = "primary_artifact" if has_primary else "unverified"

        # Optional evidence, from sources that accept a query. A hot list is
        # never consulted here: reading one because the owner named a topic
        # would be the other route wearing a different hat.
        fetched: List[Dict[str, Any]] = []
        fetch_failures: List[Dict[str, Any]] = []
        if fetch_evidence:
            for outcome in user_topic_route.collect_evidence(
                    profile, payload, adapters=self.adapters,
                    timeout=self.timeout):
                if outcome.ok:
                    fetched.extend(user_topic_route.evidence_items([outcome]))
                else:
                    fetch_failures.append(outcome.to_dict())
        if fetched:
            verification = "primary_artifact"

        positioning = alignment["alignment"]
        decision = "EXPERIMENT" if positioning == "OFF_POSITIONING" else "ACCEPT"

        candidate_doc = brief_module.candidate_document(
            candidate_id="CAND-" + digest(
                {"account": profile.account_id, "topic": topic})[:16].upper(),
            title=topic,
            thesis=_thesis(profile, {"title": topic, "category": scoring["category"]},
                           positioning),
            audience_segment=_audience_segment(profile, topic),
            decision=decision,
            positioning_alignment=positioning,
            trust_level={"primary_artifact": "HIGH"}.get(verification, "LOW"),
            components=components)
        forecast = brief_module.forecast_document(
            topic_id=candidate_doc["candidate_id"],
            profile=profile,
            verification_status=verification,
            has_primary_source=has_primary,
            assessment_basis=(
                "The topic was supplied by the account owner rather than chosen from "
                "a hot list, so the forecast is built from the material they "
                "provided."))
        refs = user_topic_route.reference_ids(payload)
        intent = ContentIntent(
            account_id=profile.account_id,
            account_profile_version=profile.profile_version,
            route_mode="USER_TOPIC",
            topic=topic,
            content_angle=None,
            source_artifact_refs=list(payload.urls),
            evidence_status="verification_required",
            approval_status="pending",
            target_pipeline=target_pipeline_for(profile),
            brief_status="draft",
            route_context=RouteContext(
                mode="USER_TOPIC",
                search_plan_id=None,
                candidate_id=None,
                topic_origin="USER_INPUT",
                user_input=topic,
                selected_at=utcnow(),
                selected_by=selected_by or "account owner",
                off_profile_override=override,
                detail={"input": payload.to_dict(),
                        "local_references": user_topic_route.local_reference_records(payload),
                        "reference_ids": refs,
                        "relevance": scoring,
                        "fetched_evidence": fetched,
                        "fetch_failures": fetch_failures},
            ),
            profile=profile.summary(),
            evidence=[{"kind": "user_reference", "url": url, "status": "supplied"}
                      for url in payload.urls] + fetched,
            profile_alignment=alignment,
        )
        package = brief_module.build_brief_package(
            intent=intent, profile=profile, candidate=candidate_doc,
            forecast=forecast,
            extra={"user_input": payload.to_dict()})
        return intent, package


def _is_primary(url: str) -> bool:
    lowered = (url or "").casefold()
    return any(marker in lowered for marker in
               ("github.com", "arxiv.org", "huggingface.co", "docs.", "developer."))


def _thesis(profile: AccountProfile, candidate: Dict[str, Any], positioning: str) -> str:
    """What the topic is, in the account's own vocabulary.

    The thesis states the subject and the pillar it serves. It makes no
    claim about the world, because at brief time there is no evidence yet
    that would support one.
    """
    title = str(candidate.get("title") or "")
    category = brief_module.CATEGORY_LABELS.get(str(candidate.get("category")),
                                                 "未分类")
    pillar = candidate.get("pillar") or ""
    parts = [f"{category}：{title}"]
    if pillar:
        parts.append(f"归属支柱 {pillar}")
    if positioning == "OFF_POSITIONING":
        parts.append("已记录为偏离定位，需人工复核")
    return "；".join(parts)


def _audience_segment(profile: AccountProfile, topic: str) -> str:
    """The core audience this topic is written for."""
    lowered = topic.casefold()
    for audience in profile.target_audience:
        if audience.casefold() in lowered:
            return audience
    if profile.target_audience:
        return profile.target_audience[0]
    return "未指定"


def uuid_marker() -> str:
    """A per-call marker, so two runs started in the same second differ."""
    import os
    import time
    return f"{os.getpid()}|{time.time_ns()}"
