import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { App } from "../../app/App";
import { createQueryJobHandler } from "../../tests/queryJobMock";

const attributes = [
  {
    attribute_id: 1,
    attribute_key: "emission_wavelength",
    attribute_name: "Emission Wavelength",
    value_type: "number",
    unit: "nm",
    description: "Peak fluorescence emission wavelength.",
  },
  {
    attribute_id: 2,
    attribute_key: "is_fluorescent",
    attribute_name: "Is Fluorescent",
    value_type: "boolean",
    unit: null,
    description: "Observed fluorescence flag.",
  },
];

const entries = {
  1: [
    {
      entry_id: 10,
      attribute_id: 1,
      entry_key: "emission_wavelength.proby_dmso",
      annotation_kind: "property",
      method_name: "Fluorimeter",
      method_version: "2.1",
      conditions: { solvent: "DMSO", temperature_c: 25 },
      is_mutable: true,
      description: "Measured emission maximum.",
    },
  ],
  2: [
    {
      entry_id: 11,
      attribute_id: 2,
      entry_key: "is_fluorescent.visual_check",
      annotation_kind: "property",
      method_name: "Visual inspection",
      method_version: null,
      conditions: {},
      is_mutable: false,
      description: null,
    },
  ],
};

function renderAt(route: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("stage 4 read-only pages", () => {
  it("browses Attributes, Entries, statistics and readable conditions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        createQueryJobHandler(
          (url) => {
            if (url === "/api/v1/attributes/query") return { items: attributes };
            if (url === "/api/v1/attributes/1/entries/query") return { items: entries[1] };
            if (url === "/api/v1/attributes/1/stats/query") {
              return {
                items: [
                  {
                    attribute_id: 1,
                    entry_id: 10,
                    entry_key: "emission_wavelength.proby_dmso",
                    value_type: "number",
                    count: 8,
                    distinct_count: 8,
                    min: 480,
                    max: 610,
                    mean: 535.25,
                    median: 530,
                    std: 35,
                    true_count: null,
                    false_count: null,
                  },
                ],
              };
            }
            return undefined;
          },
          (url) => {
            throw new Error(`Unexpected URL ${url}`);
          },
        ),
      ),
    );

    renderAt("/catalog");

    expect(await screen.findByText("emission_wavelength.proby_dmso")).toBeInTheDocument();
    expect(screen.queryByText("DMSO")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /emission_wavelength\.proby_dmso/ }),
    );
    expect(screen.getByText("DMSO")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getByText(/535\.25/)).toHaveTextContent("535.25 nm");
    expect(screen.queryByText(/\{"solvent"/)).not.toBeInTheDocument();
  });

  it("loads selected Molecule Attribute annotations only when requested", async () => {
    const clipboardWrite = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWrite },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(
        createQueryJobHandler(
          (url) => {
            if (url === "/api/v1/molecules/1/query") {
              return {
                molecule_id: 1,
                lab_id: "MLD-0001",
                canonical_smiles: "CCO",
                created_at: "2026-08-27T00:00:00Z",
              };
            }
            if (url === "/api/v1/molecules/1/attributes/query") return { items: attributes };
            if (url === "/api/v1/molecules/1/attributes/1/annotations/query") {
              return {
                items: [
                  {
                    entry_id: 10,
                    entry_key: "emission_wavelength.proby_dmso",
                    annotation_kind: "property",
                    method_name: "Fluorimeter",
                    method_version: "2.1",
                    conditions: { solvent: "DMSO", temperature_c: 25 },
                    is_mutable: true,
                    description: "Measured emission maximum.",
                    value: 512.5,
                    updated_at: "2026-08-27T01:00:00Z",
                  },
                ],
              };
            }
            return undefined;
          },
          (url) => {
            throw new Error(`Unexpected URL ${url}`);
          },
        ),
      ),
    );

    renderAt("/molecules/1");

    expect(await screen.findByRole("heading", { name: "MLD-0001" })).toBeInTheDocument();
    expect(await screen.findByText("Select an attribute to view annotations.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Emission Wavelength" })).toBeInTheDocument();
    expect(screen.queryByText("DMSO")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Molecule structure preview")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Emission Wavelength" }));
    expect(await screen.findByText(/512\.5/)).toHaveTextContent("512.5 nm");
    const card = screen.getByText(/512\.5/).closest("details");
    expect(card).not.toHaveAttribute("open");

    await userEvent.click(screen.getByText(/512\.5/));
    expect(card).toHaveAttribute("open");
    expect(screen.getByText("DMSO")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit property" })).toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: "Copy Lab ID" })[0]);
    expect(clipboardWrite).toHaveBeenCalledWith("MLD-0001");
  });
});
