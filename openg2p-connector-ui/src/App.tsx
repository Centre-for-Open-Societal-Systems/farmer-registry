import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import PipelineList from "./pages/PipelineList";
import PipelineForm from "./pages/PipelineForm";
import PipelineDetails from "./pages/PipelineDetails";
import RunsList from "./pages/RunsList";
import DLQList from "./pages/DLQList";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<PipelineList />} />
          <Route path="new" element={<PipelineForm />} />
          <Route path="edit/:id" element={<PipelineForm />} />
          <Route path="pipelines/:id" element={<PipelineDetails />} />
          <Route path="runs" element={<RunsList />} />
          <Route path="dlq" element={<DLQList />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
