import React from "react";
import { Pagination, PaginationVariant } from "@patternfly/react-core";

interface PaginationLayoutProps {
  itemCount: number;
  page: number;
  perPage: number;
  onSetPage: (page: number) => void;
  onPerPageSelect: (perPage: number) => void;
  variant?: "top" | "bottom";
}

const PaginationLayout: React.FC<PaginationLayoutProps> = ({
  itemCount,
  page,
  perPage,
  onSetPage,
  onPerPageSelect,
  variant = "top",
}) => {
  return (
    <Pagination
      itemCount={itemCount}
      page={page}
      perPage={perPage}
      onSetPage={(_evt, p) => onSetPage(p)}
      onPerPageSelect={(_evt, pp) => onPerPageSelect(pp)}
      variant={variant === "bottom" ? PaginationVariant.bottom : PaginationVariant.top}
      isCompact
    />
  );
};

export default PaginationLayout;
