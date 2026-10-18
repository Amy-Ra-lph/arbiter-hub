import React from "react";
import {
  Modal,
  ModalVariant,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@patternfly/react-core";

interface ModalWithFormLayoutProps {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: () => void;
  submitLabel?: string;
  isSubmitDisabled?: boolean;
  variant?: "small" | "medium" | "large";
  children: React.ReactNode;
}

const ModalWithFormLayout: React.FC<ModalWithFormLayoutProps> = ({
  title,
  isOpen,
  onClose,
  onSubmit,
  submitLabel = "Submit",
  isSubmitDisabled = false,
  variant = "medium",
  children,
}) => {
  const pfVariant =
    variant === "small"
      ? ModalVariant.small
      : variant === "large"
        ? ModalVariant.large
        : ModalVariant.medium;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      variant={pfVariant}
    >
      <ModalHeader title={title} />
      <ModalBody>{children}</ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={onSubmit}
          isDisabled={isSubmitDisabled}
        >
          {submitLabel}
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  );
};

export default ModalWithFormLayout;
