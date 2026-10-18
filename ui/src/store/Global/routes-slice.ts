import { createSlice, PayloadAction } from "@reduxjs/toolkit";

interface RoutesState {
  activePageName: string;
  activeFirstLevel: string;
  activeSecondLevel: string;
  breadCrumbPath: string[];
  browserTitle: string;
}

const initialState: RoutesState = {
  activePageName: "Dashboard",
  activeFirstLevel: "",
  activeSecondLevel: "",
  breadCrumbPath: [],
  browserTitle: "Arbiter Hub",
};

const routesSlice = createSlice({
  name: "routes",
  initialState,
  reducers: {
    updateActivePageName(state, action: PayloadAction<string>) {
      state.activePageName = action.payload;
      document.title = `${action.payload} | Arbiter Hub`;
    },
    updateActiveFirstLevel(state, action: PayloadAction<string>) {
      state.activeFirstLevel = action.payload;
    },
    updateActiveSecondLevel(state, action: PayloadAction<string>) {
      state.activeSecondLevel = action.payload;
    },
    updateBreadCrumbPath(state, action: PayloadAction<string[]>) {
      state.breadCrumbPath = action.payload;
    },
  },
});

export const {
  updateActivePageName,
  updateActiveFirstLevel,
  updateActiveSecondLevel,
  updateBreadCrumbPath,
} = routesSlice.actions;
export default routesSlice.reducer;
