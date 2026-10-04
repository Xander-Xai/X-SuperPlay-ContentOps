"""ContentOps media layer: provider contracts, billing gate, quality gates.

M2 added speech. M3 adds image. The shared infrastructure — the billing gate, the
credential binding, attempt records, the immutable receipt convention and the
transport layer — is provider-generic and modality-agnostic, so it is imported
here once rather than per modality.
"""

from .contract import (  # noqa: F401
    BillingBlocked,
    CapabilityNotSupported,
    MediaProvider,
    QuotaSnapshot,
    SpeechAsset,
    SpeechReceipt,
    SpeechRequest,
)
from .credentials import (  # noqa: F401
    CredentialBinding,
    CredentialBindingError,
    ResolvedCredential,
    resolve_credential,
)
from .image_contract import (  # noqa: F401
    AssetKind,
    AssetRecord,
    AssetRegistry,
    EvidenceUse,
    GeneratedAssetEvidenceError,
    ImageAsset,
    ImageOutcome,
    ImageProvider,
    ImageReceipt,
    ImageRequest,
    register_asset,
)
from .image_container import (  # noqa: F401
    ImageContainerError,
    canonical_extension_for,
    detect_image_container,
)
from .image_fingerprint import (  # noqa: F401
    DimensionRejected,
    image_fingerprint,
    validate_dimensions,
)

__all__ = [
    "AssetKind",
    "AssetRecord",
    "AssetRegistry",
    "BillingBlocked",
    "CapabilityNotSupported",
    "CredentialBinding",
    "CredentialBindingError",
    "DimensionRejected",
    "EvidenceUse",
    "GeneratedAssetEvidenceError",
    "ImageAsset",
    "ImageContainerError",
    "ImageOutcome",
    "ImageProvider",
    "ImageReceipt",
    "ImageRequest",
    "MediaProvider",
    "QuotaSnapshot",
    "ResolvedCredential",
    "SpeechAsset",
    "SpeechReceipt",
    "SpeechRequest",
    "canonical_extension_for",
    "detect_image_container",
    "image_fingerprint",
    "register_asset",
    "resolve_credential",
    "validate_dimensions",
]