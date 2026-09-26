def test_contract_exports():
    from lunch.field_06 import contract, renderer, view_model
    assert callable(contract.validate) and callable(view_model.build_view_model) and callable(renderer.render)
