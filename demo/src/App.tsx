import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Landing } from "@/routes/Landing";
import { Operator } from "@/routes/Operator";
import { Audit } from "@/routes/Audit";
import { Slo } from "@/routes/Slo";
import { Tenants } from "@/routes/Tenants";
import { Docs } from "@/routes/Docs";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="operator" element={<Operator />} />
        <Route path="audit" element={<Audit />} />
        <Route path="slo" element={<Slo />} />
        <Route path="tenants" element={<Tenants />} />
        <Route path="docs/*" element={<Docs />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
