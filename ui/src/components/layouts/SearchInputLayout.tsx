import React from "react";
import { SearchInput } from "@patternfly/react-core";

interface SearchInputLayoutProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

const SearchInputLayout: React.FC<SearchInputLayoutProps> = ({
  value,
  onChange,
  placeholder = "Search...",
}) => {
  return (
    <SearchInput
      placeholder={placeholder}
      value={value}
      onChange={(_event, val) => onChange(val)}
      onClear={() => onChange("")}
    />
  );
};

export default SearchInputLayout;
