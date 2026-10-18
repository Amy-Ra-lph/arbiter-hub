import { configureStore } from "@reduxjs/toolkit";
import { api } from "src/services/api";
import routesReducer from "./Global/routes-slice";
import alertsReducer from "./Global/alerts-slice";

export const store = configureStore({
  reducer: {
    [api.reducerPath]: api.reducer,
    routes: routesReducer,
    alerts: alertsReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(api.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
