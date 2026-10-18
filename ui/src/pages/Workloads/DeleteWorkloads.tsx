import React from "react";
import {
  Modal,
  ModalVariant,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@patternfly/react-core";
import { useDeleteWorkloadMutation } from "src/services/rpcWorkloads";

interface DeleteWorkloadsProps {
  isOpen: boolean;
  onClose: () => void;
  selectedIds: string[];
  onComplete: () => void;
}

const DeleteWorkloads: React.FC<DeleteWorkloadsProps> = ({
  isOpen,
  onClose,
  selectedIds,
  onComplete,
}) => {
  const [deleteWorkload, { isLoading }] = useDeleteWorkloadMutation();

  const handleDelete = async () => {
    for (const id of selectedIds) {
      await deleteWorkload(id);
    }
    onComplete();
    onClose();
  };

  const count = selectedIds.length;

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant={ModalVariant.small}>
      <ModalHeader title="Delete Workloads" />
      <ModalBody>
        Are you sure you want to delete {count} workload{count !== 1 ? "s" : ""}?
        This action cannot be undone. All attestation records and state
        transitions for the selected workloads will be permanently removed.
      </ModalBody>
      <ModalFooter>
        <Button
          variant="danger"
          onClick={handleDelete}
          isDisabled={isLoading}
          isLoading={isLoading}
        >
          Delete {count} workload{count !== 1 ? "s" : ""}
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  );
};

export default DeleteWorkloads;
