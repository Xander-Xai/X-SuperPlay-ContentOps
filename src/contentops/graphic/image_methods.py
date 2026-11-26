"""Canonical image-generation methods selectable by the graphic workflow."""

IMAGE_METHODS = (
    "codex_imagegen",
    "ian_xiaohei_codex",
    "minimax_subscription",
)

RETIRED_IMAGE_METHODS = frozenset({
    "manual_chatgpt_web",
    "api",
    "local_svg_html",
})

CODEX_METHODS = frozenset({"codex_imagegen", "ian_xiaohei_codex"})
MINIMAX_METHOD = "minimax_subscription"
IAN_SKILL_ID = "ian-xiaohei-illustrations"
GENERATION_RECEIPT_SCHEMA = "contentops.graphic-image-generation/v1"
REMOTE_GENERATED_LICENSE = "GENERATED-REMOTE-REVIEWED"
