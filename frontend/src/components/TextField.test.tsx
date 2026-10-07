import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextField } from "./TextField";

describe("TextField", () => {
  it("opens a date field's picker on a click anywhere in it, and still calls onClick", async () => {
    const onClick = vi.fn();
    render(<TextField aria-label="Date" type="date" onClick={onClick} />);
    const field = screen.getByLabelText("Date") as HTMLInputElement;
    const showPicker = vi.fn();
    field.showPicker = showPicker;

    await userEvent.click(field);
    expect(showPicker).toHaveBeenCalledOnce();
    expect(onClick).toHaveBeenCalledOnce();
    expect(field).toHaveClass("cursor-pointer");
  });

  it("leaves a plain text field alone", async () => {
    render(<TextField aria-label="Nom" />);
    const field = screen.getByLabelText("Nom") as HTMLInputElement;
    const showPicker = vi.fn();
    field.showPicker = showPicker;

    await userEvent.click(field);
    expect(showPicker).not.toHaveBeenCalled();
    expect(field).not.toHaveClass("cursor-pointer");
  });
});
