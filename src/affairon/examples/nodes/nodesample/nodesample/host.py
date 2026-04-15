from affairon import AffairMain, listen
from nodesample.app import demo


@listen(AffairMain)
def run(_affair: AffairMain) -> dict[str, object]:
    result = demo()
    print(f"Members: {result['members']}")
    print(f"Messages logged: {result['log_count']}")
    print(f"Alice sent: {result['alice_msgs']}, Bob sent: {result['bob_msgs']}")
    print(f"Clock ticks: {result['clock']}")
    return result
