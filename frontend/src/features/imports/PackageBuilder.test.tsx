import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryJobHandler, json } from "../../tests/queryJobMock";
import { PackageBuilder } from "./PackageBuilder";

const attributes = [
  {
    attribute_id: 1,
    attribute_key: "absorption_wavelength",
    attribute_name: "Absorption Wavelength",
    value_type: "number",
    unit: "nm",
    description: "分子紫外最强吸收波长",
  },
];

const entriesIndex = [
  {
    entry_id: 261,
    entry_key: "absorption_wavelength.deepmpp.CS(C)=O",
    attribute_key: "absorption_wavelength",
    attribute_name: "Absorption Wavelength",
    annotation_kind: "prediction",
    method_name: "DeepMPP",
    method_version: null,
    conditions: { solvent_smiles: "CS(C)=O" },
    is_mutable: false,
    description: "DeepMPP 在 CS(C)=O 条件下预测的 Absorption Wavelength。",
  },
];

const sourceFiles = [
  { name: "results.csv", size_bytes: 2048, modified_at: "2026-09-20T00:00:00Z" },
];

const profile = {
  name: "results.csv",
  encoding: "utf-8",
  delimiter: ",",
  columns: [
    { index: 0, name: "SMILES", value_type: "text", filled_rows: 2, empty_rows: 0 },
    { index: 1, name: "Abs_pred", value_type: "number", filled_rows: 2, empty_rows: 0 },
  ],
  total_rows: 2,
  preview_rows: [
    ["CCO", "311.5"],
    ["CCC", "400"],
  ],
};

const preflightResult = {
  dry_run: true,
  package_name: "deepmpp_batch_v1",
  attributes_existing: 1,
  attributes_new: 0,
  entries_existing: 1,
  entries_new: 0,
  annotation_rows: 7,
  linkable_molecules: 5,
  unlinkable_molecules: 2,
  in_file_duplicates: 0,
  already_in_database: 1,
  expected_inserts: 4,
  rejected_rows: 3,
  warnings: ["1 rows or values were skipped while building the package"],
};

function renderBuilder() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PackageBuilder />
    </QueryClientProvider>,
  );
}

function stubBuilderApi(options: { onBuild?: (body: unknown) => unknown } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      createQueryJobHandler(
        (url, init) => {
          if (url === "/api/v1/attributes/query") return { items: attributes };
          if (url === "/api/v1/entries/index/query") return { items: entriesIndex };
          if (url === "/api/v1/packages/build") {
            const body: unknown = JSON.parse(String(init?.body));
            return options.onBuild ? options.onBuild(body) : preflightResult;
          }
          return undefined;
        },
        (url) => {
          if (url === "/api/v1/source-files") return json(sourceFiles);
          if (url === "/api/v1/source-files/results.csv/profile") return json(profile);
          throw new Error(`Unexpected URL ${url}`);
        },
      ),
    ),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("package builder", () => {
  it("reads a source file, maps it onto registered definitions and preflights a build", async () => {
    const buildBodies: unknown[] = [];
    stubBuilderApi({
      onBuild: (body) => {
        buildBodies.push(body);
        return preflightResult;
      },
    });

    renderBuilder();

    await userEvent.click(await screen.findByRole("button", { name: /^results\.csv/ }));

    expect(await screen.findByText("311.5")).toBeInTheDocument();
    expect(screen.getByText("2 rows · 2 columns · encoding utf-8 · delimiter “,”")).toBeInTheDocument();
    expect(screen.getByLabelText("Molecule identifier column")).toHaveValue("0");

    await userEvent.selectOptions(
      screen.getByLabelText("Existing Attribute"),
      "absorption_wavelength",
    );
    expect(screen.getByText(/分子紫外最强吸收波长/)).toBeInTheDocument();

    await userEvent.selectOptions(
      screen.getByLabelText("Existing Entry"),
      "absorption_wavelength.deepmpp.CS(C)=O",
    );
    expect(screen.getByText(/DeepMPP 在 CS\(C\)=O/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Package name"), "deepmpp_batch_v1");
    await userEvent.type(screen.getByLabelText("Processor name"), "DeepMPP processor");
    await userEvent.click(screen.getByRole("button", { name: "Preflight" }));

    expect(await screen.findByText("Preflight result")).toBeInTheDocument();
    expect(screen.getAllByText("1 existing · 0 new")).toHaveLength(2);
    expect(screen.getByText("Expected inserts")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(
      screen.getByText("1 rows or values were skipped while building the package"),
    ).toBeInTheDocument();

    await waitFor(() => expect(buildBodies).toHaveLength(1));
    expect(buildBodies[0]).toMatchObject({
      package_name: "deepmpp_batch_v1",
      source_file: "results.csv",
      identifier_column_index: 0,
      processor_name: "DeepMPP processor",
      dry_run: true,
      mappings: [
        {
          column_index: 1,
          column_name: "Abs_pred",
          attribute: { mode: "existing", attribute_key: "absorption_wavelength" },
          entry: { mode: "existing", entry_key: "absorption_wavelength.deepmpp.CS(C)=O" },
        },
      ],
    });
  });

  it("keeps reused definitions read-only and reveals the create-new fields", async () => {
    stubBuilderApi();

    renderBuilder();

    await userEvent.click(await screen.findByRole("button", { name: /^results\.csv/ }));
    await screen.findByText("311.5");

    const card = screen.getByRole("article");
    expect(within(card).queryByLabelText("Name")).not.toBeInTheDocument();

    await userEvent.click(within(card).getAllByLabelText("Create new")[0]);

    expect(within(card).getByLabelText("Name")).toBeInTheDocument();
    expect(within(card).getByLabelText("Type")).toHaveValue("number");
    expect(within(card).queryByText(/Registered:/)).not.toBeInTheDocument();
    expect(within(card).getByLabelText("Existing Entry")).toBeDisabled();

    await userEvent.type(within(card).getAllByLabelText("Key")[0], "emission_wavelength");
    await userEvent.click(within(card).getAllByLabelText("Create new")[1]);

    expect(within(card).getAllByLabelText("Key")[1]).toHaveValue("emission_wavelength.method");

    await userEvent.type(within(card).getAllByLabelText("Method")[0], "DeepMPP");
    await userEvent.type(
      within(card).getAllByLabelText("Conditions")[0],
      "solvent_smiles=CS(C)=O",
    );
    expect(within(card).getAllByLabelText("Key")[1]).toHaveValue("emission_wavelength.method");
  });
});
