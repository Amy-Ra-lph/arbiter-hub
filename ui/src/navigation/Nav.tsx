import React from "react";
import { Nav as PFNav, NavExpandable, NavItem, NavList } from "@patternfly/react-core";
import { useLocation, useNavigate } from "react-router-dom";
import { navSections } from "./NavRoutes";
import { useAppDispatch } from "src/store/hooks";
import { updateActivePageName } from "src/store/Global/routes-slice";

const Navigation: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();

  const onSelect = (
    _event: React.FormEvent<HTMLInputElement>,
    result: { itemId: number | string; groupId: number | string | null }
  ) => {
    const path = result.itemId as string;
    navigate(path);
    const section = navSections.find((s) =>
      s.items.some((i) => i.path === path)
    );
    const item = section?.items.find((i) => i.path === path);
    if (item) {
      dispatch(updateActivePageName(item.label));
    }
  };

  return (
    <PFNav onSelect={onSelect} aria-label="Navigation">
      <NavList>
        {navSections.map((section) => {
          if (section.items.length === 1 && section.label === "Dashboard") {
            const item = section.items[0];
            return (
              <NavItem
                key={item.path}
                itemId={item.path}
                isActive={location.pathname === item.path}
              >
                {item.label}
              </NavItem>
            );
          }
          return (
            <NavExpandable
              key={section.label}
              title={section.label}
              groupId={section.label}
              isActive={section.items.some(
                (i) => location.pathname === i.path
              )}
              isExpanded={section.items.some(
                (i) => location.pathname === i.path || location.pathname.startsWith(i.path + "/")
              )}
            >
              {section.items.map((item) => (
                <NavItem
                  key={item.path}
                  itemId={item.path}
                  isActive={
                    location.pathname === item.path ||
                    location.pathname.startsWith(item.path + "/")
                  }
                >
                  {item.label}
                </NavItem>
              ))}
            </NavExpandable>
          );
        })}
      </NavList>
    </PFNav>
  );
};

export default Navigation;
