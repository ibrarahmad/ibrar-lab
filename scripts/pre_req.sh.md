# pre_req.sh

This script installs the prerequisites for building PostgreSQL and running the `pg_script.py` script. It detects the operating system and installs the necessary packages for Debian-based and Red Hat-based systems.

## Usage

```bash
./pre_req.sh
```

The script will:

1.  Detect the operating system.
2.  Install the necessary build dependencies for PostgreSQL.
3.  Install the required Python libraries for `pg_script.py`.

### Supported Operating Systems

-   Debian-based (Debian, Ubuntu)
-   Red Hat-based (CentOS, RHEL, Fedora, Rocky)

The script must be run with `sudo` privileges to install packages.
