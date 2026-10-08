import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ConfirmProvider, useConfirm } from "./Confirm";

function Probe({ onAnswer }: { onAnswer: (v: boolean) => void }) {
  const ask = useConfirm();
  return <button onClick={async () => onAnswer(await ask("Удалить?", { confirmLabel: "Удалить", danger: true }))}>open</button>;
}

describe("ConfirmProvider", () => {
  it("resolves true on the confirm button and false on cancel", async () => {
    const answers: boolean[] = [];
    const user = userEvent.setup();
    render(<ConfirmProvider><Probe onAnswer={(v) => answers.push(v)} /></ConfirmProvider>);
    await user.click(screen.getByText("open"));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Удалить?");
    await user.click(screen.getByRole("button", { name: "Удалить" }));
    await user.click(screen.getByText("open"));
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(answers).toEqual([true, false]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});
