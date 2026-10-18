import React, { useEffect, useState } from "react";
import { Label } from "@patternfly/react-core";

interface TTLCountdownProps {
  lastAttestedAt: string | null;
  staleTtlSeconds: number;
}

function formatRemaining(seconds: number): string {
  if (seconds <= 0) return "stale";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

const TTLCountdown: React.FC<TTLCountdownProps> = ({
  lastAttestedAt,
  staleTtlSeconds,
}) => {
  const [remaining, setRemaining] = useState<number>(0);

  useEffect(() => {
    const calc = () => {
      if (!lastAttestedAt) {
        setRemaining(0);
        return;
      }
      const elapsed =
        (Date.now() - new Date(lastAttestedAt).getTime()) / 1000;
      setRemaining(Math.max(0, staleTtlSeconds - elapsed));
    };
    calc();
    const interval = setInterval(calc, 10000);
    return () => clearInterval(interval);
  }, [lastAttestedAt, staleTtlSeconds]);

  if (!lastAttestedAt) {
    return <Label color="grey">never attested</Label>;
  }

  const isStale = remaining <= 0;
  const isWarning = remaining > 0 && remaining < 900;

  return (
    <Label color={isStale ? "orange" : isWarning ? "yellow" : "green"}>
      {formatRemaining(remaining)}
    </Label>
  );
};

export default TTLCountdown;
