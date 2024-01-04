#!/bin/sh

TOPDIR=$(pwd)
LSRDIR="ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME"
mkdir -p "$TOX_WORK_DIR/$LSRDIR"
cp -a "$TOPDIR"/* "$TOPDIR/.ansible-lint" "$TOX_WORK_DIR/$LSRDIR"
