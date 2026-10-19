import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import { store } from "src/store/store";
import { OIDCProvider } from "src/auth/OIDCProvider";
import App from "src/App";
import "src/main.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Provider store={store}>
      <OIDCProvider>
        <App />
      </OIDCProvider>
    </Provider>
  </React.StrictMode>
);
