from worlds.LauncherComponents import Component, Type, components, launch


def run_client(*args: str) -> None:
    from .client.launch import launch_client

    launch(
        launch_client,
        name="Lords of Shadow Client",
        args=args,
    )


components.append(
    Component(
        "Lords of Shadow Client",
        func=run_client,
        game_name="Castlevania: Lords of Shadow",
        component_type=Type.CLIENT,
        supports_uri=True,
    )
)
