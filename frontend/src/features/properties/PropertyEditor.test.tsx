import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PropertyEditor } from "./PropertyEditor";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderEditor(overrides: Partial<React.ComponentProps<typeof PropertyEditor>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PropertyEditor
        currentValue={510}
        entryId={10}
        entryKey="emission.property"
        moleculeId={1}
        unit="nm"
        valueType="number"
        {...overrides}
      />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PropertyEditor", () => {
  it("submits a typed value and source, then follows the update job", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      const url = String(input);
      if (url === "/api/v1/molecules/1/properties/10")
        return Promise.resolve(json({ job_id: "property-job" }, 202));
      if (url === "/api/v1/jobs/property-job") {
        return Promise.resolve(
          json({
            job_id: "property-job",
            job_type: "property_update",
            status: "completed",
            progress: 1,
            message: "Property updated",
            error_message: null,
            payload: {},
            result: {
              molecule_id: 1,
              entry_id: 10,
              value_number: 525.5,
              value_text: null,
              value_boolean: null,
              source: "experiment review",
              created: false,
              updated_at: "2026-08-27T00:00:00Z",
            },
            created_at: "2026-08-27T00:00:00Z",
            updated_at: "2026-08-27T00:00:00Z",
          }),
        );
      }
      throw new Error(`Unexpected URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderEditor();
    await user.click(screen.getByRole("button", { name: "Edit property" }));
    await user.clear(screen.getByLabelText("New value (nm)"));
    await user.type(screen.getByLabelText("New value (nm)"), "525.5");
    await user.type(screen.getByLabelText("Update source"), "experiment review");
    await user.click(screen.getByRole("button", { name: "Submit update" }));

    await waitFor(() => {
      const mutation = fetchMock.mock.calls.find(([url]) => String(url).includes("/properties/10"));
      expect(mutation).toBeDefined();
      expect(JSON.parse(String(mutation?.[1]?.body))).toEqual({
        value_number: 525.5,
        source: "experiment review",
      });
    });
    const success = await waitFor(() => {
      const element = document.querySelector(".property-editor__success");
      expect(element).toBeInTheDocument();
      return element;
    });
    expect(success).toHaveTextContent("Property updated.");
    expect(success).toHaveTextContent("Source: experiment review");
  });

  it("uses dedicated controls for text and boolean Property values", async () => {
    const { rerender } = renderEditor({ currentValue: "note", unit: null, valueType: "text" });
    await userEvent.click(screen.getByRole("button", { name: "Edit property" }));
    expect(screen.getByLabelText("New value").tagName).toBe("TEXTAREA");

    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <PropertyEditor
          currentValue={true}
          entryId={11}
          entryKey="flag.property"
          moleculeId={1}
          valueType="boolean"
        />
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Edit property" }));
    expect(screen.getByLabelText("New value").tagName).toBe("SELECT");
  });
});
