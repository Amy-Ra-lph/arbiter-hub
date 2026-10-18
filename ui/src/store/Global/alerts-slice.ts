import { createSlice, PayloadAction } from "@reduxjs/toolkit";

export interface AlertInfo {
  id: string;
  variant: "success" | "danger" | "warning" | "info";
  title: string;
  description?: string;
}

interface AlertsState {
  alerts: AlertInfo[];
}

const initialState: AlertsState = {
  alerts: [],
};

const alertsSlice = createSlice({
  name: "alerts",
  initialState,
  reducers: {
    addAlert(state, action: PayloadAction<Omit<AlertInfo, "id">>) {
      state.alerts.push({
        ...action.payload,
        id: crypto.randomUUID(),
      });
    },
    removeAlert(state, action: PayloadAction<string>) {
      state.alerts = state.alerts.filter((a) => a.id !== action.payload);
    },
  },
});

export const { addAlert, removeAlert } = alertsSlice.actions;
export default alertsSlice.reducer;
