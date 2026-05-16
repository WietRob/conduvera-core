"""Matrix OS harness scaffolding and gateway metadata."""

from curaops.harness.gateway import (
    EditorSurfaceDescriptor,
    GatewayCapability,
    HarnessGatewayRegistry,
    RunnerDescriptor,
    ToolDescriptor,
    list_editor_surfaces,
    list_gateway_capabilities,
    list_runners,
    list_tools,
)
from curaops.harness.scaffolding import (
    SCAFFOLDING_SLICES,
    ScaffoldingSlice,
    get_scaffolding_slice,
    list_scaffolding_slices,
)

__all__ = [
    "EditorSurfaceDescriptor",
    "GatewayCapability",
    "HarnessGatewayRegistry",
    "RunnerDescriptor",
    "SCAFFOLDING_SLICES",
    "ScaffoldingSlice",
    "ToolDescriptor",
    "get_scaffolding_slice",
    "list_editor_surfaces",
    "list_gateway_capabilities",
    "list_runners",
    "list_scaffolding_slices",
    "list_tools",
]
