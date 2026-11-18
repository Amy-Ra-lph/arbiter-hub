# Kickstart for Arbiter Hub IPA Primary node — Fedora 44 bootc
# Placeholders (__KEY__) are replaced by deploy.sh from ipa-config.env

lang en_US.UTF-8
keyboard us
timezone UTC --utc
rootpw --plaintext __ADMIN_PASSWORD__
network --bootproto=dhcp --hostname=__FQDN__
firewall --disabled
selinux --enforcing

ostreecontainer --url __IMAGE_SOURCE__

%post --erroronfail
mkdir -p /etc/idm-image-mode
cat > /etc/idm-image-mode/config.env <<'CONFIGEOF'
__CONFIG_ENV_CONTENT__
CONFIGEOF
chmod 600 /etc/idm-image-mode/config.env

mkdir -p /root/.ssh
echo '__SSH_PUBKEY__' >> /root/.ssh/authorized_keys
chmod 700 /root/.ssh
chmod 600 /root/.ssh/authorized_keys

systemctl enable sshd
systemctl enable idm-firstboot || systemctl enable arbiter-idm-firstboot || true
%end
