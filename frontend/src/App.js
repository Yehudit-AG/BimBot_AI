import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from 'react-query';
import Header from './components/Header';
import DrawingUpload from './pages/DrawingUpload';
import LayerManagement from './pages/LayerManagement';
import JobDashboard from './pages/JobDashboard';
import './App.css';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <div className="App">
          <Header />
          <main className="container">
            <Routes>
              <Route path="/" element={<DrawingUpload />} />
              <Route path="/drawings/:drawingId/layers" element={<LayerManagement />} />
              <Route path="/jobs/:jobId" element={<JobDashboard />} />
            </Routes>
          </main>
        </div>
      </Router>
    </QueryClientProvider>
  );
}

export default App;