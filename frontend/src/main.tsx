import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router";

import { createQueryClient } from "./app/queryClient";
import { routes } from "./app/routes";
import "./index.css";

const router = createBrowserRouter(routes);
const queryClient = createQueryClient();

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("#root element missing from index.html");

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
