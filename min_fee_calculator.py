import csv
import pdfkit

from collections import OrderedDict
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, Template
from portfolio import Account
from portfolio import format_currency
from portfolio import Portfolio

billing_file = 'data/billing.csv'
accounts_file = 'data/account_values.csv'
netflows_file = 'data/netflows.csv'
mgmt_fees_file = 'data/mgmt_fees.csv'
q1_fees_file = 'data/q1_fees.csv'
unmanaged_file = 'data/unmanaged.csv'

portfolios_by_legacy_id = OrderedDict()
portfolios_by_jxr_code = OrderedDict()
accounts_by_account_number = OrderedDict()

# Add portfolios to maps with portfolio-level information.
with open(billing_file, 'rb') as portfolio_file:
    reader = csv.DictReader(portfolio_file)
    for row in reader:
        portfolio_name = row['portfolio']
        billing_spec = row['billing_spec']
        if billing_spec == '':
            print("portfolio " + row['account_number'] + " does not have a billing spec. Ignoring.")
            continue
        name_array = portfolio_name.split(', ')
        if len(name_array) != 2:
            print("this is a weird name: " + portfolio_name)
            clean_portfolio_name = input('type corrected name: ')
        else:
            clean_portfolio_name = name_array[1] + ' ' + name_array[0]
        address_array = [row['address_1']]
        if row['address_2']:
            address_array.append(row['address_2'])
        address_array.append(row['city'] + ', ' + row['state'] + ' ' + row['zip_code'])
        address_as_html = '<br>'.join(address_array)
        curr_portfolio = (Portfolio(clean_portfolio_name)
                .set_address(address_as_html)
                .set_jxr_code(row['account_number'])
                .set_legacy_id(row['legacy_id'])
                .set_billing_spec(row['billing_spec']))
        portfolios_by_legacy_id[row['legacy_id']] = curr_portfolio
        portfolios_by_jxr_code[row['account_number']] = curr_portfolio

# Add q1 fees to portfolios
with open(q1_fees_file, 'rb') as q1_fees:
    reader = csv.DictReader(q1_fees)
    for row in reader:
        account_number = row['account_number']
        try:
            float(row['q1_fees'])
        except:
            print("Q1 fees entry for account number " + account_number + " is '" + row['q1_fees'] + "'. Ignoring.")
            portfolio = portfolios_by_jxr_code.pop(account_number, None)
            if portfolio:
                portfolios_by_legacy_id.pop(portfolio.legacy_id, None)
        if account_number in portfolios_by_jxr_code:
            curr_portfolio = portfolios_by_jxr_code[account_number]
            curr_portfolio.set_dec_fee(row['q1_fees'])

# Add netflows and values to portfolios
with open(netflows_file, 'rb') as netflows_file:
    reader = csv.DictReader(netflows_file)
    for row in reader:
        clean_jxr = row['jxr_code'].strip()
        if clean_jxr in portfolios_by_jxr_code:
            curr_portfolio = portfolios_by_jxr_code[clean_jxr]
            (curr_portfolio.set_netflow(row['netflows'])
                           .set_value(row['end_value'])
                           .set_previous_value(row['begin_value'])
            )

# Add accounts to portfolio. Populate accounts_map to add mgmt fees later.
with open(accounts_file, 'rb') as account_values:
    reader = csv.DictReader(account_values)
    for row in reader:
        curr_portfolio = row['hidden_portfolio_id']
        if curr_portfolio in portfolios_by_legacy_id:
            account_name = ' '.join([row['first_name'], row['last_name']])
            try:
                account_value = float(row['value'])
            except:
                print(account_name + ' ' + row['account_type'] +  " has value 0, ignoring.")
                continue
            curr_account = (
                Account(account_name)
                    .set_account_type(row['account_type'])
                    .set_account_number(row['account_number'])
                    .set_billing_account(row['billing_account_number'])
                    .set_parent_portfolio(portfolios_by_legacy_id[curr_portfolio])
                    .set_value(row['value'])
            )
            accounts_by_account_number[row['account_number'].strip()] = curr_account
            portfolios_by_legacy_id[curr_portfolio].accounts.append(curr_account)

# Remove unmanaged assets from account values
with open(unmanaged_file, 'rb') as unmanaged_assets:
    reader = csv.DictReader(unmanaged_assets)
    for row in reader:
        curr_account_num = row['account_number'].strip()
        if curr_account_num in accounts_by_account_number:
            curr_account = accounts_by_account_number[curr_account_num]
            unmanaged_amount = float(row['value'])
            curr_account.set_value(curr_account.get_value() - unmanaged_amount)
            if curr_account.get_value() == 0:
                print("account " + curr_account.name + ", " + curr_account.account_type + " is fully unmanaged")

# Add mgmt fees to every account
with open(mgmt_fees_file, 'rb') as mgmt_fees:
    reader = csv.DictReader(mgmt_fees)
    for row in reader:
        curr_account_num = row['account_number'].strip()
        if curr_account_num in accounts_by_account_number:
            curr_account = accounts_by_account_number[curr_account_num]
            curr_account.add_mgmt_fee(row['fee_amount'])

file_loader = FileSystemLoader('templates')
env = Environment(loader=file_loader)
t = env.get_template('billing_statement.html')

total_to_bill = 0
for key, port in portfolios_by_legacy_id.items():
    port.calculate_current_fee()
    if port.disabled:
        print("disabled portfolio: " + port.name)
        continue
    total_to_bill += port.amount_to_bill()
    html_output = 'output/' + port.jxr_code + '.html'
    pdf_name = port.jxr_code + "_03232020"
    if port.min_fee_applies():
        pdf_name += "_min_fee"
    #  Last Name_JXR CODE_Addendum.pdf
    pdf_output = 'statements/' + pdf_name + '.pdf'
    with open(html_output, 'w') as f:
        print >> f, t.render(portfolio=port,
                             format_currency=format_currency,
                             date=datetime.today().strftime("%B %d, %Y"))

    pdfkit.from_file(html_output, pdf_output, options={ 'quiet': '' })
print("billing total: " + format_currency(total_to_bill))


