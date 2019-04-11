from typing import Union, List

from spotlight import errors as err
from spotlight import rules as rls


class Validator:
    class Plugin:
        def rules(self) -> List[rls.BaseRule]:
            return []

    """
    Creates an instance of the Validator class.
    """

    def __init__(self, plugins: List[Plugin] = None):

        self._output = {}
        self._flat_list = []

        self.overwrite_messages = {}
        self.overwrite_fields = {}
        self.overwrite_values = {}

        self._implicit_rules = []
        self._registered_rules = []
        self._available_rules = {}

        self._setup_default_rules()
        self._setup_plugins(plugins or [])

    def _setup_default_rules(self):
        self.register_rules(self._default_rules())

    @staticmethod
    def _default_rules() -> List[rls.BaseRule]:
        return [
            rls.RequiredRule(),
            rls.RequiredWithoutRule(),
            rls.RequiredWithRule(),
            rls.RequiredIfRule(),
            rls.NotWithRule(),
            rls.FilledRule(),
            rls.EmailRule(),
            rls.UrlRule(),
            rls.IpRule(),
            rls.MinRule(),
            rls.MaxRule(),
            rls.InRule(),
            rls.AlphaNumRule(),
            rls.AlphaNumSpaceRule(),
            rls.StringRule(),
            rls.IntegerRule(),
            rls.BooleanRule(),
            rls.JsonRule(),
            rls.ListRule(),
            rls.Uuid4Rule(),
            rls.AcceptedRule(),
            rls.StartsWithRule(),
        ]

    def _setup_rule(self, rule):
        self._available_rules[rule.name] = rule
        if rule.implicit:
            self._implicit_rules.append(rule.name)

    @staticmethod
    def _dynamically_add_static_validation_methods(rule):
        for attr in dir(rule):
            if attr.startswith("valid_"):
                validation_method = getattr(rule, attr)
                setattr(Validator, attr, staticmethod(validation_method))

    def register_rules(self, rules: [rls.BaseRule]):
        for rule in rules:
            self.register_rule(rule)

    def register_rule(self, rule: rls.BaseRule):
        self._registered_rules.append(rule)
        self._setup_rule(rule)

    def validate(
        self, input_: Union[dict, object], input_rules: dict, flat: bool = False
    ):
        self._output = input_rules.copy()
        self.loop_over_rules(input_, input_rules)
        self.clean_output(self._output)
        if flat:
            self._flat_list = []
            self.flatten_output(self._output)
            return self._flat_list
        return self._output

    def clean_output(self, output):
        keys_to_be_removed = []
        for item in output:

            if type(output[item]) is dict:
                self.clean_output(output[item])
            elif type(output[item]) is str:
                keys_to_be_removed.append(item)

        for key in keys_to_be_removed:
            output.pop(key)

    def loop_over_rules(
        self, input_: Union[dict, object], input_rules: dict
    ) -> Union[dict, list]:
        """
        Validate input with given rules.

        Parameters
        ----------
        input_ : Union[dict, object]
            Dict or object with input that needs to be validated.
            For example: {"email": "john.doe@example.com"},
            Input(email="john.doe@example.com")
        input_rules : Union[dict, object]
            Dict with validation rules for given input.
            For example: {"email": "required|email|unique:user,email"}

        """

        # Transform input to dictionary
        if not isinstance(input_, dict):
            input_ = input_.__dict__

        # Iterate over fields
        for field in input_rules:
            if type(input_rules.get(field)) is dict:
                self.loop_over_rules(input_[field], input_rules.get(field))
                continue

            rules = input_rules.get(field).split("|")
            # Iterate over rules
            for rule in rules:
                # Verify that rule isn't empty
                if rule != "":
                    # Split rule name and rule_values
                    rule_name, *rule_values = rule.split(":")

                    # Check if field is validatable
                    if self._is_validatable(rule_name, field, input_):
                        # Check if rule exists
                        if rule_name in self._available_rules:
                            matched_rule = self._available_rules.get(rule_name)

                            # Execute correct validation method
                            value = input_.get(field)

                            # Rule
                            if isinstance(matched_rule, rls.Rule):
                                passed = matched_rule.passes(field, value)
                            # Dependent Rule
                            elif isinstance(matched_rule, rls.DependentRule):
                                passed = matched_rule.passes(
                                    field, value, rule_values, input_
                                )

                            # If rule didn't pass, add error
                            if not passed:
                                self._add_error(
                                    rule=rule_name,
                                    field=field,
                                    error=matched_rule.message(),
                                    fields=matched_rule.message_fields,
                                )

                                # Stop validation
                                if matched_rule.stop:
                                    break
                        else:
                            raise Exception(err.RULE_NOT_FOUND.format(rule=rule_name))

    def _is_validatable(self, rule, field, input_):
        return self._present_or_rule_is_implicit(rule, field, input_)

    def _present_or_rule_is_implicit(self, rule, field, input_):
        return self._validate_present(field, input_) or self._is_implicit(rule)

    def _validate_present(self, field, input_):
        return field in input_ and input_.get(field) is not None

    def _is_implicit(self, rule):
        return rule in self._implicit_rules

    def _add_error(self, rule, field, error, fields=None):
        self.place_error_in_output(field, rule, error, self._output, fields)

    def place_error_in_output(self, field, rule, error, output, fields):
        for item in output:
            if type(output[item]) is dict:
                self.place_error_in_output(field, rule, error, output[item], fields)

            if item == field:
                if type(output[field]) is str:
                    output[field] = []

                combined_field = field + "." + rule

                if field in self.overwrite_messages:
                    error = self.overwrite_messages[field]

                if combined_field in self.overwrite_messages:
                    error = self.overwrite_messages[combined_field]

                if field in self.overwrite_fields:
                    for key, value in fields.items():
                        if value in self.overwrite_fields:
                            fields[key] = self.overwrite_fields[value]

                if field in self.overwrite_values:
                    fields["values"] = self.overwrite_values[field]["values"]

                output[field].append(error.format(**fields))

    def flatten_output(self, output):
        for item in output:
            if type(output[item]) == dict:
                self.flatten_output(output[item])
                continue
            for error in output[item]:
                self._flat_list.append(error)

    @staticmethod
    def valid_email(email) -> bool:
        return rls.EmailRule.valid_email(email)

    @staticmethod
    def valid_url(url) -> bool:
        return rls.UrlRule.valid_url(url)

    @staticmethod
    def valid_ip(ip) -> bool:
        return rls.IpRule.valid_ip(ip)

    @staticmethod
    def valid_uuid4(uuid) -> bool:
        return rls.Uuid4Rule.valid_uuid4(uuid)

    @staticmethod
    def valid_string(string) -> bool:
        return rls.StringRule.valid_string(string)

    @staticmethod
    def valid_integer(integer) -> bool:
        return rls.IntegerRule.valid_integer(integer)

    @staticmethod
    def valid_boolean(boolean) -> bool:
        return rls.BooleanRule.valid_boolean(boolean)

    @staticmethod
    def valid_json(value) -> bool:
        return rls.JsonRule.valid_json(value)

    @staticmethod
    def valid_alpha_num(value) -> bool:
        return rls.AlphaNumRule.valid_alpha_num(value)

    @staticmethod
    def valid_alpha_num_space(value) -> bool:
        return rls.AlphaNumSpaceRule.valid_alpha_num_space(value)

    @staticmethod
    def valid_list(value) -> bool:
        return rls.ListRule.valid_list(value)

    def _setup_plugins(self, plugins: List[Plugin]):
        for plugin in plugins:
            self.register_rules(plugin.rules())
