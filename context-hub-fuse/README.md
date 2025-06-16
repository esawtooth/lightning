# Context Hub FUSE

This crate exposes the contents of a Context Hub data directory as a FUSE filesystem.

## Building

```
cargo build --release
```

The release binary is placed under `target/release/mount`.

## Mounting

Create a mountpoint and run the `mount` binary. You must have the FUSE
package installed and permission to use `fusermount` (either run with
`sudo` or add your user to the `fuse` group).

```
mkdir /tmp/hub
sudo target/release/mount /tmp/hub
```

Use `fusermount -u /tmp/hub` to unmount.

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTEXT_USER` | user ID for new documents | `user1` |
| `DATA_DIR` | directory containing Context Hub documents | `data` |

## Example

After mounting, files and folders behave like a normal filesystem. Reading
or writing a file transparently updates the underlying documents.

```
CONTEXT_USER=alice DATA_DIR=./data \
  sudo target/release/mount /tmp/hub

echo "hello" > /tmp/hub/note.txt
cat /tmp/hub/note.txt
```
