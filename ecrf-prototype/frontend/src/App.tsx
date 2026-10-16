import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import DataEntry from "./pages/DataEntry";
import Protocols from "./pages/Protocols";
import Review from "./pages/Review";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Protocols />} />
        <Route path="/review/:id" element={<Review />} />
        <Route path="/data/:id" element={<DataEntry />} />
        <Route path="/dashboard/:id" element={<Dashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
