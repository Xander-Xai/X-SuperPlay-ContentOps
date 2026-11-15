"use strict";

const $ = (id) => document.getElementById(id);
const accountSelect = $("account");
const summary = $("profile-summary");
const form = $("task-form");
const submitButton = $("submit");
const statusLine = $("status");
const resultPanel = $("result");
const receiptView = $("receipt");
const draftView = $("draft");
let profiles = [];
let lastFingerprint = "";
let idempotencyKey = "";
let evidenceFingerprint = "";
let evidenceKey = "";
let projectViewRevision = 0;
let runtimeCandidates = [];

$("windows-runtime-candidates").addEventListener("change", (event) => {
  const selected = runtimeCandidates[Number(event.target.value) - 1];
  if (!event.target.value || !selected) return;
  $("windows-runtime-project").value = selected.project;
  $("windows-runtime-package").value = selected.package;
});

// Keep only a digest and opaque key in this tab so a reload can retry the
// same request without persisting the brief itself in browser storage.
async function retryIdentity(kind, request) {
  const bytes = new TextEncoder().encode(JSON.stringify(request));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const fingerprint = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")).join("");
  const storageKey = `contentops-easel-${kind}-retry-v1`;
  let stored = null;
  try { stored = JSON.parse(sessionStorage.getItem(storageKey)); } catch { /* storage unavailable */ }
  const key = stored && stored.fingerprint === fingerprint &&
    typeof stored.key === "string" && /^[0-9a-f-]{36}$/.test(stored.key)
    ? stored.key : crypto.randomUUID();
  try { sessionStorage.setItem(storageKey, JSON.stringify({ fingerprint, key })); } catch { /* in-memory retry remains available */ }
  return { fingerprint, key };
}

function clearRetryIdentity(kind) {
  try { sessionStorage.removeItem(`contentops-easel-${kind}-retry-v1`); } catch { /* storage unavailable */ }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  let payload;
  try { payload = await response.json(); }
  catch { throw new Error(`服务器返回无效响应 (${response.status})`); }
  if (!response.ok) {
    const reason = payload.detail || payload.error || `请求失败 (${response.status})`;
    const error = new Error(payload.failure_receipt ? `${reason}（失败回执：${payload.failure_receipt}）` : reason);
    error.failureRecord = payload.failure_record;
    throw error;
  }
  return payload;
}

function appendPair(term, value) {
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = Array.isArray(value) ? value.join(" → ") : String(value ?? "未声明");
  summary.append(dt, dd);
}

function showProfile() {
  const profile = profiles.find((item) => item.slug === accountSelect.value);
  summary.replaceChildren();
  if (!profile) return;
  appendPair("账号", `${profile.name} · ${profile.role}`);
  appendPair("账号承诺", profile.promise);
  appendPair("叙事模式", profile.narrative.mode);
  appendPair("语速", `${profile.narrative.speech_rate_cpm} 字/分钟`);
  appendPair("目标时长", `${profile.narrative.target_duration_s[0]}–${profile.narrative.target_duration_s[1]} 秒`);
  appendPair("叙事模板", profile.narrative.template);
  appendPair("CTA", profile.narrative.cta);
  appendPair("画面配比", profile.visual.composition.map((item) => `${item.role} ${item.pct}%`));
  const selected = profile.slug;
  $("profile-detail").textContent = "正在生成画像…";
  requestJson(`/api/contentops/profiles/${encodeURIComponent(selected)}`)
    .then((detail) => {
      if (accountSelect.value !== selected) return;
      $("profile-detail").textContent = Object.entries(detail.files)
        .map(([name, content]) => `===== ${name} =====\n${content}`).join("\n\n");
    })
    .catch((error) => {
      if (accountSelect.value === selected) $("profile-detail").textContent = error instanceof Error ? error.message : "画像读取失败";
    });
}

async function loadProfiles() {
  statusLine.textContent = "正在读取账号 DNA…";
  const payload = await requestJson("/api/contentops/profiles");
  profiles = payload.profiles;
  accountSelect.replaceChildren();
  for (const profile of profiles) {
    const option = document.createElement("option");
    option.value = profile.slug;
    option.textContent = profile.name;
    accountSelect.append(option);
  }
  showProfile();
  await loadProjects();
  const excluded = Array.isArray(payload.excluded_accounts) ? payload.excluded_accounts.length : 0;
  statusLine.textContent = profiles.length
    ? `画像已绑定${excluded ? `；${excluded} 个账号因 DNA 不完整不可选` : ""}`
    : "没有符合视频画像契约的账号";
  submitButton.disabled = profiles.length === 0;
}

async function loadProjects() {
  const selected = accountSelect.value;
  const list = $("account-projects");
  const message = $("project-list-status");
  list.replaceChildren();
  if (!selected) { message.textContent = "没有可选账号。"; return; }
  message.textContent = "正在读取匹配项目…";
  try {
    const query = new URLSearchParams({ account: selected });
    const result = await requestJson(`/api/contentops/projects?${query}`);
    if (accountSelect.value !== selected) return;
    for (const slug of result.projects) {
      const option = document.createElement("option");
      option.value = slug;
      list.append(option);
    }
    message.textContent = result.projects.length
      ? `找到 ${result.projects.length} 个匹配项目；可从输入框选择。`
      : "未找到匹配项目；项目须在 project.yaml 中声明当前账号。";
  } catch (error) {
    if (accountSelect.value === selected) message.textContent = error instanceof Error ? error.message : "项目列表读取失败";
  }
}

function clearProjectView() {
  projectViewRevision += 1;
  $("recent-tasks").replaceChildren();
  $("recent-failures").replaceChildren();
  $("recent-agent-workspaces").replaceChildren();
  $("recent-proposals").replaceChildren();
  $("recent-windows-reviews").replaceChildren();
  $("lookup-task-id").value = "";
  $("lookup-failure-id").value = "";
  $("proposal-sha256").value = "";
  $("project-readiness").hidden = true;
  $("project-readiness").textContent = "";
  resultPanel.hidden = true;
  receiptView.textContent = "";
  draftView.textContent = "";
  $("supporting-artifacts").textContent = "";
  $("supporting-panel").hidden = true;
}

accountSelect.addEventListener("change", () => {
  $("project").value = "";
  clearProjectView();
  showProfile();
  loadProjects();
});
$("refresh-projects").addEventListener("click", loadProjects);
$("project").addEventListener("input", clearProjectView);

$("check-project").addEventListener("click", async () => {
  const view = $("project-readiness");
  const revision = projectViewRevision;
  const account = accountSelect.value;
  const project = $("project").value.trim();
  const query = new URLSearchParams({ account, project });
  view.hidden = false;
  view.textContent = "正在读取项目材料…";
  try {
    const result = await requestJson(`/api/contentops/project-readiness?${query}`);
    if (projectViewRevision !== revision || accountSelect.value !== account || $("project").value.trim() !== project) return;
    view.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    if (projectViewRevision !== revision || accountSelect.value !== account || $("project").value.trim() !== project) return;
    view.textContent = error instanceof Error ? error.message : "项目材料读取失败";
  }
});

async function showTask(taskId, account, project) {
  const revision = projectViewRevision;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(taskId)) {
    throw new Error("任务 ID 格式无效");
  }
  const query = new URLSearchParams({ account, project });
  const [receipt, draft] = await Promise.all([
    requestJson(`/api/contentops/draft-task/${taskId}?${query}`),
    requestJson(`/api/contentops/draft-task/${taskId}/draft?${query}`),
  ]);
  let artifacts = null;
  if (receipt.status === "OFFLINE_EVIDENCE_DRAFT") {
    artifacts = await requestJson(`/api/contentops/draft-task/${taskId}/artifacts?${query}`);
  }
  if (projectViewRevision !== revision || accountSelect.value !== account || $("project").value.trim() !== project) {
    throw new Error("账号或项目已更改，请重新读取任务");
  }
  receiptView.textContent = JSON.stringify(receipt, null, 2);
  draftView.textContent = draft.content;
  $("supporting-artifacts").textContent = artifacts ? JSON.stringify(artifacts, null, 2) : "";
  $("supporting-panel").hidden = !artifacts;
  $("lookup-task-id").value = taskId;
  resultPanel.hidden = false;
}

$("list-tasks").addEventListener("click", async () => {
  const button = $("list-tasks");
  const account = accountSelect.value;
  const project = $("project").value.trim();
  const revision = projectViewRevision;
  const list = $("recent-tasks");
  button.disabled = true;
  try {
    const query = new URLSearchParams({ account, project });
    const result = await requestJson(`/api/contentops/draft-tasks?${query}`);
    if (projectViewRevision !== revision || accountSelect.value !== account || $("project").value.trim() !== project) return;
    list.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = result.tasks.length ? "选择一个任务" : "没有可读取的离线任务";
    list.append(placeholder);
    for (const task of result.tasks) {
      const option = document.createElement("option");
      option.value = task.task_id;
      option.textContent = `${task.status} · ${task.task_id}`;
      list.append(option);
    }
    const workspaces = $("recent-agent-workspaces");
    workspaces.replaceChildren();
    const workspacePlaceholder = document.createElement("option");
    workspacePlaceholder.value = "";
    workspacePlaceholder.textContent = result.agent_workspaces.length ? "选择一个准备记录" : "没有可读取的准备记录";
    workspaces.append(workspacePlaceholder);
    for (const workspace of result.agent_workspaces) {
      const option = document.createElement("option");
      option.value = workspace.run_id;
      option.textContent = `准备记录 · ${workspace.run_id}`;
      workspaces.append(option);
    }
    const proposalList = $("recent-proposals");
    proposalList.replaceChildren();
    const proposalPlaceholder = document.createElement("option");
    proposalPlaceholder.value = "";
    proposalPlaceholder.textContent = result.agent_proposals.length ? "选择历史申请资料" : "没有已保存的申请资料";
    proposalList.append(proposalPlaceholder);
    for (const proposal of result.agent_proposals) {
      const option = document.createElement("option");
      option.value = proposal.proposal_sha256;
      option.dataset.runId = proposal.run_id;
      option.textContent = `任务 ${proposal.run_id} · ${proposal.proposal_sha256.slice(0, 12)}（当前状态未检查）`;
      proposalList.append(option);
    }
    const reviews = $("recent-windows-reviews");
    reviews.replaceChildren();
    const reviewPlaceholder = document.createElement("option");
    reviewPlaceholder.value = "";
    reviewPlaceholder.textContent = result.windows_reviews.length ? "选择历史审查回执" : "没有可读取的审查回执";
    reviews.append(reviewPlaceholder);
    for (const review of result.windows_reviews) {
      const option = document.createElement("option");
      option.value = review.review_id;
      option.textContent = `${review.review_id} · 任务 ${review.run_id}`;
      reviews.append(option);
    }
    const failures = $("recent-failures");
    failures.replaceChildren();
    const failurePlaceholder = document.createElement("option");
    failurePlaceholder.value = "";
    failurePlaceholder.textContent = result.failures.length ? "选择一个失败回执" : "没有可读取的失败回执";
    failures.append(failurePlaceholder);
    for (const failure of result.failures) {
      const option = document.createElement("option");
      option.value = failure.attempt_id;
      option.textContent = `${failure.reason || "FAILED"} · ${failure.attempt_id}`;
      failures.append(option);
    }
    const unavailable = result.unavailable_count || 0;
    const unavailableTotal = unavailable + result.agent_unavailable_count + result.windows_review_unavailable_count + result.proposal_unavailable_count;
    statusLine.textContent = `找到 ${result.tasks.length} 个离线任务、${result.agent_workspaces.length} 个准备记录、${result.agent_proposals.length} 个申请资料、${result.windows_reviews.length} 个 Windows 审查回执、${result.failures.length} 个失败回执（各最多检查 50 个）${unavailableTotal ? `；${unavailableTotal} 个记录不可读取` : ""}`;
  } catch (error) {
    if (projectViewRevision !== revision) return;
    list.replaceChildren();
    $("recent-agent-workspaces").replaceChildren();
    $("recent-proposals").replaceChildren();
    $("recent-windows-reviews").replaceChildren();
    $("recent-failures").replaceChildren();
    statusLine.textContent = error instanceof Error ? error.message : "查找任务失败";
  } finally { button.disabled = false; }
});
$("recent-tasks").addEventListener("change", () => { $("lookup-task-id").value = $("recent-tasks").value; });
$("recent-agent-workspaces").addEventListener("change", () => { $("lookup-task-id").value = $("recent-agent-workspaces").value; });
$("recent-proposals").addEventListener("change", () => {
  const option = $("recent-proposals").selectedOptions[0];
  if (!option || !option.value) return;
  $("proposal-sha256").value = option.value;
  $("lookup-task-id").value = option.dataset.runId;
});
$("recent-failures").addEventListener("change", () => { $("lookup-failure-id").value = $("recent-failures").value; });

$("lookup-task").addEventListener("click", async () => {
  const button = $("lookup-task");
  const revision = projectViewRevision;
  button.disabled = true;
  resultPanel.hidden = true;
  statusLine.textContent = "正在读取任务…";
  try {
    await showTask($("lookup-task-id").value.trim(), accountSelect.value, $("project").value.trim());
    if (projectViewRevision !== revision) return;
    statusLine.textContent = "已读取任务草稿和回执";
  } catch (error) {
    if (projectViewRevision !== revision) return;
    statusLine.textContent = error instanceof Error ? error.message : "读取任务失败";
  } finally {
    button.disabled = false;
  }
});

$("lookup-failure").addEventListener("click", async () => {
  const attempt = $("lookup-failure-id").value.trim();
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(attempt)) {
    statusLine.textContent = "失败回执编号格式无效";
    return;
  }
  const button = $("lookup-failure");
  const account = accountSelect.value;
  const project = $("project").value.trim();
  button.disabled = true;
  try {
    const query = new URLSearchParams({ account, project, kind: "failure" });
    const record = await requestJson(`/api/contentops/draft-task/${attempt}?${query}`);
    if (accountSelect.value !== account || $("project").value.trim() !== project) throw new Error("账号或项目已更改，请重新读取回执");
    receiptView.textContent = JSON.stringify(record, null, 2);
    draftView.textContent = "此尝试未生成可用草稿。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = "已读取失败回执";
  } catch (error) {
    statusLine.textContent = error instanceof Error ? error.message : "读取失败回执失败";
  } finally { button.disabled = false; }
});

$("lookup-agent").addEventListener("click", async () => {
  const id = $("lookup-task-id").value.trim();
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)) {
    statusLine.textContent = "任务 ID 格式无效";
    return;
  }
  const button = $("lookup-agent");
  const account = accountSelect.value;
  const project = $("project").value.trim();
  button.disabled = true;
  try {
    const query = new URLSearchParams({ account, project, kind: "agent" });
    const record = await requestJson(`/api/contentops/draft-task/${id}?${query}`);
    if (accountSelect.value !== account || $("project").value.trim() !== project) throw new Error("账号或项目已更改，请重新读取任务");
    receiptView.textContent = JSON.stringify(record, null, 2);
    draftView.textContent = "Agent 执行未授权，尚无真实执行草稿。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = record.input_state === "STALE"
      ? "任务输入已过期；可选择新建准备，再重新准备任务输入"
      : "已读取 Agent 任务状态";
  } catch (error) {
    statusLine.textContent = error instanceof Error ? error.message : "读取任务状态失败";
  } finally { button.disabled = false; }
});

$("review-windows-sandbox").addEventListener("click", async () => {
  const revision = projectViewRevision;
  const button = $("review-windows-sandbox");
  const request = { account: accountSelect.value, project: $("project").value.trim(),
                    run_id: $("lookup-task-id").value.trim(),
                    runtime_project: $("windows-runtime-project").value.trim(),
                    package: $("windows-runtime-package").value.trim() };
  button.disabled = true;
  statusLine.textContent = "正在核对任务和 Windows 运行包…";
  try {
    const result = await requestJson("/api/contentops/windows-sandbox-review", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    if (projectViewRevision !== revision || accountSelect.value !== request.account || $("project").value.trim() !== request.project) return;
    receiptView.textContent = JSON.stringify(result, null, 2);
    draftView.textContent = "仅生成沙箱审查摘要；隔离未证明，Agent 未启动。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = "Windows 配置已生成；隔离未验证、执行未授权";
  } catch (error) {
    if (projectViewRevision !== revision) return;
    statusLine.textContent = error instanceof Error ? error.message : "Windows 沙箱审查失败";
  } finally { button.disabled = false; }
});

$("lookup-windows-review").addEventListener("click", async () => {
  const reviewId = $("recent-windows-reviews").value;
  const account = accountSelect.value;
  const project = $("project").value.trim();
  const button = $("lookup-windows-review");
  if (!reviewId) { statusLine.textContent = "请先选择历史审查回执"; return; }
  button.disabled = true;
  try {
    const query = new URLSearchParams({ account, project, kind: "windows-review" });
    const result = await requestJson(`/api/contentops/draft-task/${reviewId}?${query}`);
    if (accountSelect.value !== account || $("project").value.trim() !== project) throw new Error("账号或项目已更改，请重新读取");
    receiptView.textContent = JSON.stringify(result, null, 2);
    draftView.textContent = "这是历史审查记录；当前状态未重新核对，Agent 未获执行授权。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = "已读取历史审查回执；当前状态未检查";
  } catch (error) {
    statusLine.textContent = error instanceof Error ? error.message : "读取审查回执失败";
  } finally { button.disabled = false; }
});

$("lookup-agent-result").addEventListener("click", async () => {
  const attempt = $("lookup-task-id").value.trim();
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(attempt)) {
    statusLine.textContent = "结果回执编号格式无效";
    return;
  }
  const button = $("lookup-agent-result");
  const account = accountSelect.value;
  const project = $("project").value.trim();
  button.disabled = true;
  try {
    const query = new URLSearchParams({ account, project, kind: "agent-result" });
    const result = await requestJson(`/api/contentops/draft-task/${attempt}?${query}`);
    if (accountSelect.value !== account || $("project").value.trim() !== project) throw new Error("账号或项目已更改，请重新读取结果");
    receiptView.textContent = JSON.stringify(result.receipt, null, 2);
    draftView.textContent = result.draft || "该结果没有草稿。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = "已读取未验证结果；Agent 执行未证明";
  } catch (error) {
    statusLine.textContent = error instanceof Error ? error.message : "读取结果失败";
  } finally { button.disabled = false; }
});

$("cancel-agent").addEventListener("click", async () => {
  const button = $("cancel-agent");
  const request = { account: accountSelect.value, project: $("project").value.trim(),
                    run_id: $("lookup-task-id").value.trim() };
  button.disabled = true;
  try {
    const result = await requestJson("/api/contentops/agent-cancel", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    if (accountSelect.value !== request.account || $("project").value.trim() !== request.project) throw new Error("账号或项目已更改；取消记录保存在原项目");
    receiptView.textContent = JSON.stringify(result, null, 2);
    draftView.textContent = "已取消准备好的任务；没有运行 Agent。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = "已取消未执行的任务";
  } catch (error) {
    statusLine.textContent = error instanceof Error ? error.message : "取消失败";
  } finally { button.disabled = false; }
});

$("collect-agent").addEventListener("click", async () => {
  const revision = projectViewRevision;
  const button = $("collect-agent");
  const request = { account: accountSelect.value, project: $("project").value.trim(),
                    run_id: $("lookup-task-id").value.trim(), exit_code: Number($("agent-exit-code").value) };
  button.disabled = true;
  try {
    const record = await requestJson("/api/contentops/agent-collect", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    if (projectViewRevision !== revision || accountSelect.value !== request.account || $("project").value.trim() !== request.project) return;
    receiptView.textContent = JSON.stringify(record, null, 2);
    draftView.textContent = "结果已收集；请用回执编号读取草稿。来源和实际执行尚未验证。";
    $("lookup-task-id").value = record.attempt_id;
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = "候选结果已收集（执行未证明）";
  } catch (error) {
    if (projectViewRevision !== revision) return;
    statusLine.textContent = error instanceof Error ? error.message : "候选结果收集失败";
  } finally { button.disabled = false; }
});

$("reset-agent-retry").addEventListener("click", () => {
  clearRetryIdentity("agent-workspace");
  statusLine.textContent = "已选择新建准备；点击准备 Agent 任务输入生成新快照";
});

$("prepare-proposal").addEventListener("click", async () => {
  const revision = projectViewRevision;
  const button = $("prepare-proposal");
  const request = { account: accountSelect.value, project: $("project").value.trim(),
    run_id: $("lookup-task-id").value.trim(), service_mode: $("proposal-service-mode").value,
    service: $("proposal-service").value.trim(),
    endpoint: $("proposal-endpoint").value.trim(), max_cost: $("proposal-cost").value.trim(),
    currency: $("proposal-currency").value.trim().toUpperCase(), save: true };
  button.disabled = true;
  try {
    const result = await requestJson("/api/contentops/agent-proposal", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    if (projectViewRevision !== revision || $("lookup-task-id").value.trim() !== request.run_id) return;
    receiptView.textContent = JSON.stringify(result, null, 2);
    $("proposal-sha256").value = result.proposal.proposal_sha256;
    draftView.textContent = "仅供审查；尚未授权，也未调用服务。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = "申请资料已保存；隔离和执行授权均未完成";
  } catch (error) {
    if (projectViewRevision !== revision || $("lookup-task-id").value.trim() !== request.run_id) return;
    statusLine.textContent = error instanceof Error ? error.message : "申请资料整理失败";
  } finally { button.disabled = false; }
});

$("inspect-approval").addEventListener("click", async () => {
  const revision = projectViewRevision;
  const button = $("inspect-approval");
  const request = { account: accountSelect.value, project: $("project").value.trim(),
    run_id: $("lookup-task-id").value.trim(), proposal_sha256: $("proposal-sha256").value.trim() };
  button.disabled = true;
  try {
    const result = await requestJson("/api/contentops/agent-approval-inspection", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    if (projectViewRevision !== revision || $("lookup-task-id").value.trim() !== request.run_id
        || $("proposal-sha256").value.trim() !== request.proposal_sha256) return;
    receiptView.textContent = JSON.stringify(result, null, 2);
    draftView.textContent = "仅核对绑定；完整授权和隔离尚未证明。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    const labels = { REVOKED: "审批已撤销", USES_EXHAUSTED: "审批额度已用尽",
      INVALID_WINDOW: "审批时间范围无效", NOT_YET_VALID: "审批尚未生效",
      EXPIRED: "审批已过期", SUBJECT_UNSET: "主机未配置执行身份",
      SUBJECT_MISMATCH: "主机执行身份与审批不一致", PENDING_FULL_GATE: "绑定已读取，仍待完整授权判断" };
    statusLine.textContent = `${labels[result.precheck] || "审批状态未知"}；未消费授权、未执行任务`;
  } catch (error) {
    if (projectViewRevision !== revision || $("lookup-task-id").value.trim() !== request.run_id
        || $("proposal-sha256").value.trim() !== request.proposal_sha256) return;
    statusLine.textContent = error instanceof Error ? error.message : "审批绑定核对失败";
  } finally { button.disabled = false; }
});

$("read-proposal").addEventListener("click", async () => {
  const revision = projectViewRevision;
  const button = $("read-proposal");
  const request = { action: "read", account: accountSelect.value, project: $("project").value.trim(),
    run_id: $("lookup-task-id").value.trim(), proposal_sha256: $("proposal-sha256").value.trim() };
  button.disabled = true;
  try {
    const result = await requestJson("/api/contentops/agent-proposal", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    if (projectViewRevision !== revision || $("lookup-task-id").value.trim() !== request.run_id
        || $("proposal-sha256").value.trim() !== request.proposal_sha256) return;
    receiptView.textContent = JSON.stringify(result, null, 2);
    draftView.textContent = "历史申请资料；审批尚未检查，也未授权执行。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = `任务输入状态：${result.task_state}；准备状态：${result.preparation}`;
  } catch (error) {
    if (projectViewRevision !== revision || $("lookup-task-id").value.trim() !== request.run_id
        || $("proposal-sha256").value.trim() !== request.proposal_sha256) return;
    statusLine.textContent = error instanceof Error ? error.message : "申请资料读取失败";
  } finally { button.disabled = false; }
});

$("prepare-agent").addEventListener("click", async () => {
  const revision = projectViewRevision;
  const button = $("prepare-agent");
  const request = { account: accountSelect.value, project: $("project").value.trim(), brief: $("brief").value.trim() };
  button.disabled = true;
  statusLine.textContent = "正在准备 Agent 输入…";
  try {
    const identity = await retryIdentity("agent-workspace", request);
    const record = await requestJson("/api/contentops/agent-workspace", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...request, idempotency_key: identity.key }),
    });
    if (projectViewRevision !== revision || accountSelect.value !== request.account || $("project").value.trim() !== request.project) return;
    receiptView.textContent = JSON.stringify(record, null, 2);
    $("lookup-task-id").value = record.run_id;
    draftView.textContent = "任务输入已准备；Agent 尚未运行。";
    $("supporting-panel").hidden = true;
    resultPanel.hidden = false;
    statusLine.textContent = `Agent 输入已准备（${record.run_id}）；执行未授权`;
  } catch (error) {
    if (projectViewRevision !== revision) return;
    statusLine.textContent = error instanceof Error ? error.message : "输入准备失败";
  } finally { button.disabled = false; }
});

$("build-evidence-draft").addEventListener("click", async () => {
  const request = { account: accountSelect.value, project: $("project").value.trim() };
  const revision = projectViewRevision;
  const button = $("build-evidence-draft");
  button.disabled = true;
  statusLine.textContent = "正在从已批准材料生成离线草稿…";
  resultPanel.hidden = true;
  $("supporting-panel").hidden = true;
  try {
    const identity = await retryIdentity("evidence", request);
    if (identity.fingerprint !== evidenceFingerprint || !evidenceKey) {
      evidenceFingerprint = identity.fingerprint;
      evidenceKey = identity.key;
    }
    const submitted = await requestJson("/api/contentops/evidence-draft", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...request, idempotency_key: evidenceKey }),
    });
    if (projectViewRevision !== revision) return;
    await showTask(submitted.task_id, request.account, request.project);
    if (projectViewRevision !== revision) return;
    statusLine.textContent = `离线证据草稿已写入项目（${submitted.task_id}）`;
    evidenceKey = "";
    clearRetryIdentity("evidence");
  } catch (error) {
    if (projectViewRevision !== revision) return;
    statusLine.textContent = error instanceof Error ? error.message : "任务失败";
    if (error.failureRecord) {
      $("lookup-failure-id").value = error.failureRecord.attempt_id || "";
      receiptView.textContent = JSON.stringify(error.failureRecord, null, 2);
      draftView.textContent = "任务未生成草稿。";
      resultPanel.hidden = false;
    }
  } finally {
    button.disabled = false;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const request = {
    account: accountSelect.value,
    project: $("project").value.trim(),
    brief: $("brief").value.trim(),
  };
  const revision = projectViewRevision;
  submitButton.disabled = true;
  statusLine.textContent = "正在写入离线草稿框架…";
  resultPanel.hidden = true;
  $("supporting-panel").hidden = true;
  try {
    const identity = await retryIdentity("scaffold", request);
    if (identity.fingerprint !== lastFingerprint || !idempotencyKey) {
      lastFingerprint = identity.fingerprint;
      idempotencyKey = identity.key;
    }
    const submitted = await requestJson("/api/contentops/draft-task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...request, idempotency_key: idempotencyKey }),
    });
    if (projectViewRevision !== revision) return;
    await showTask(submitted.task_id, request.account, request.project);
    if (projectViewRevision !== revision) return;
    statusLine.textContent = `离线框架已写入项目（${submitted.task_id}）`;
  } catch (error) {
    if (projectViewRevision !== revision) return;
    statusLine.textContent = error instanceof Error ? error.message : "任务失败";
    if (error.failureRecord) {
      $("lookup-failure-id").value = error.failureRecord.attempt_id || "";
      receiptView.textContent = JSON.stringify(error.failureRecord, null, 2);
      draftView.textContent = "任务未生成草稿。";
      resultPanel.hidden = false;
    }
  } finally {
    submitButton.disabled = false;
  }
});

loadProfiles().catch((error) => {
  statusLine.textContent = error instanceof Error ? error.message : "画像读取失败";
  submitButton.disabled = true;
});

requestJson("/api/contentops/status")
  .then((status) => {
    if (status.mode !== "OFFLINE_DRAFTS_ONLY") {
      $("host-status").textContent = "工作台状态未知";
      return;
    }
    const sandbox = status.windows_sandbox;
    const candidates = sandbox && Array.isArray(sandbox.runtime_candidates) ? sandbox.runtime_candidates : [];
    runtimeCandidates = candidates;
    const runtimeSelect = $("windows-runtime-candidates");
    candidates.forEach((candidate, index) => {
      const option = document.createElement("option");
      option.value = String(index + 1);
      option.textContent = `${candidate.project} / ${candidate.package}（未验证）`;
      runtimeSelect.append(option);
    });
    if (candidates.length === 1 && !$("windows-runtime-project").value && !$("windows-runtime-package").value) {
      $("windows-runtime-project").value = candidates[0].project;
      $("windows-runtime-package").value = candidates[0].package;
      runtimeSelect.value = "1";
    }
    $("host-status").textContent = sandbox && sandbox.platform === "WINDOWS"
      ? `离线草稿模式 · 仅有内嵌执行原型，gateway 路径未实现 · 启动器禁用 · 隔离未证明 · Agent 未授权${candidates.length ? ` · 发现 ${candidates.length} 个未验证运行包` : ""}${sandbox.flatbuffers === "MISSING" ? " · 缺少 flatbuffers" : ""}`
      : "离线草稿模式 · 网关未探测 · 真实 Agent 执行未授权";
  })
  .catch(() => { $("host-status").textContent = "工作台状态读取失败"; });

requestJson("/api/contentops/skills/video-script")
  .then((skill) => { $("skill-detail").textContent = skill.content; })
  .catch((error) => { $("skill-detail").textContent = error instanceof Error ? error.message : "技能读取失败"; });
