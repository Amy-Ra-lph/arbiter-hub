import React from "react";

interface ArbiterLogoProps {
  className?: string;
}

const ArbiterLogo: React.FC<ArbiterLogoProps> = ({ className }) => {
  return (
    <div className={className} style={{ display: "flex", alignItems: "center", gap: "10px" }}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 32 32"
        width="36"
        height="36"
        aria-hidden="true"
      >
        {/* Fedora logo — infinity hat shape */}
        <path
          d="M16 2C8.28 2 2 8.28 2 16s6.28 14 14 14 14-6.28 14-14S23.72 2 16 2zm0 2c6.63 0 12 5.37 12 12 0 2.12-.55 4.12-1.52 5.85l-5.2-3.85c.46-.9.72-1.93.72-3 0-3.31-2.69-6-6-6s-6 2.69-6 6c0 1.07.26 2.1.72 3l-5.2 3.85A11.94 11.94 0 0 1 4 16C4 9.37 9.37 4 16 4zm0 7c2.76 0 5 2.24 5 5s-2.24 5-5 5-5-2.24-5-5 2.24-5 5-5z"
          fill="#3C6EB4"
        />
      </svg>
      <span style={{ fontSize: "18px", fontWeight: 600, color: "var(--pf-t--global--text--color--regular)" }}>
        Arbiter Hub
      </span>
    </div>
  );
};

export default ArbiterLogo;
