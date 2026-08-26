import { BrowserRouter } from "react-router";
import { AuthProvider } from "./auth/AuthProvider";
import App from "./app/App";

export default function RootApp() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  );
}
