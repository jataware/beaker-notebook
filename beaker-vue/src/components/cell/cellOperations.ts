import type { BeakerQueryEvent } from "@jataware/beaker-client";

const terminalEvents = [
    "error",
    "response"
]

export const isLastEventTerminal = (cellEvents: BeakerQueryEvent[]) => {
    if (cellEvents?.length > 0) {
        return terminalEvents.includes(cellEvents[cellEvents.length - 1].type);
    }
    return false;
};
