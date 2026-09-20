import { QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { BrowserRouter } from "react-router";

import { JobTrackingProvider } from "../features/jobs/JobTrackingProvider";
import { createQueryClient } from "./queryClient";

interface AppProvidersProps {
  children: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps) {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <JobTrackingProvider>
        <BrowserRouter>{children}</BrowserRouter>
      </JobTrackingProvider>
    </QueryClientProvider>
  );
}
